"""Service module for IP-based brute-force protection.

Pure-function service. All state lives in the SQLAlchemy models defined in
``BOFS/default/models.py`` (``BannedIp``, ``LoginAttempt``, ``AdminTrustedIp``)
and in ``current_app.config``.

Every function here is safe to call when ``BRUTE_FORCE_PROTECTION`` is False —
the ``is_banned`` / ``record_*`` paths short-circuit so callers don't need to
guard each call site individually.
"""

from datetime import timedelta
from typing import Optional

from flask import current_app, request
from sqlalchemy.exc import SQLAlchemyError

from BOFS.globals import db
from BOFS.util import utcnow_naive


def get_client_ip() -> str:
    """Return the request's client IP.

    With ``BEHIND_REVERSE_PROXY = true``, ``ProxyFix`` has rewritten
    ``request.remote_addr`` from the proxy headers; we return it directly.
    With ``BEHIND_REVERSE_PROXY = false`` we still return
    ``request.remote_addr`` and deliberately ignore ``X-Real-IP`` /
    ``X-Forwarded-For`` because they're spoofable when nothing trusted is
    in front of us.
    """
    return request.remote_addr or ""


def _ban_schedule() -> list:
    schedule = current_app.config.get(
        'BRUTE_FORCE_BAN_SCHEDULE',
        [1, 2, 5, 15, 60, 360, 1440, 10080],
    )
    if not schedule:
        return [60]
    return list(schedule)


def _ban_minutes_for(ip: str) -> int:
    """Look up the next ban duration for *ip* by counting prior ``BannedIp``
    rows (active or expired) and indexing into ``BRUTE_FORCE_BAN_SCHEDULE``.
    The final entry sticks for additional bans.
    """
    schedule = _ban_schedule()
    prior = db.session.query(db.BannedIp).filter(
        db.BannedIp.ipAddress == ip
    ).count()
    return schedule[min(prior, len(schedule) - 1)]


def is_trusted(ip: str) -> bool:
    """True if *ip* is in static ``TRUSTED_IPS`` config or in
    ``AdminTrustedIp``."""
    if not ip:
        return False
    static = current_app.config.get('TRUSTED_IPS', []) or []
    if ip in static:
        return True
    row = db.session.get(db.AdminTrustedIp, ip)
    return row is not None


def is_banned(ip: str) -> bool:
    """True if *ip* has an unexpired ``BannedIp`` row.

    Returns False when ``BRUTE_FORCE_PROTECTION`` is False or *ip* is trusted.
    """
    if not current_app.config.get('BRUTE_FORCE_PROTECTION', True):
        return False
    if not ip or is_trusted(ip):
        return False
    now = utcnow_naive()
    return db.session.query(db.BannedIp).filter(
        db.BannedIp.ipAddress == ip,
        db.BannedIp.expiresAt != None,  # noqa: E711
        db.BannedIp.expiresAt > now,
    ).count() > 0


def seconds_until_unban(ip: str) -> int:
    """Seconds until the active ban for *ip* expires, or 60 if no ban is found
    (a sensible default for ``Retry-After``).
    """
    now = utcnow_naive()
    row = db.session.query(db.BannedIp).filter(
        db.BannedIp.ipAddress == ip,
        db.BannedIp.expiresAt != None,  # noqa: E711
        db.BannedIp.expiresAt > now,
    ).order_by(db.BannedIp.expiresAt.desc()).first()
    if row is None:
        return 60
    # Normalise tz-aware expiry (from imported data) to naive so the
    # subtraction below doesn't raise TypeError on mixed-tz inputs.
    expiry = row.expiresAt
    if expiry.tzinfo is not None:
        expiry = expiry.replace(tzinfo=None)
    delta = (expiry - now).total_seconds()
    return max(int(delta), 1)


def _prune_login_attempts(ip: Optional[str] = None) -> None:
    """Delete ``LoginAttempt`` rows older than the window. If *ip* is given,
    only that IP's rows; otherwise all expired rows."""
    window = current_app.config.get('BRUTE_FORCE_WINDOW_MINUTES', 15)
    cutoff = utcnow_naive() - timedelta(minutes=window)
    q = db.session.query(db.LoginAttempt).filter(
        db.LoginAttempt.attemptedAt < cutoff
    )
    if ip is not None:
        q = q.filter(db.LoginAttempt.ipAddress == ip)
    q.delete(synchronize_session=False)


def record_failure(ip: str) -> None:
    """Append a ``LoginAttempt`` row. If the failure count for *ip* in the
    last ``BRUTE_FORCE_WINDOW_MINUTES`` reaches ``BRUTE_FORCE_MAX_ATTEMPTS``,
    insert a ``BannedIp`` row using the progressive schedule and clear the
    IP's pending ``LoginAttempt`` rows.

    No-op if protection is disabled or *ip* is trusted.
    """
    if not current_app.config.get('BRUTE_FORCE_PROTECTION', True):
        return
    if not ip or is_trusted(ip):
        return

    now = utcnow_naive()

    try:
        attempt = db.LoginAttempt()
        attempt.ipAddress = ip
        attempt.attemptedAt = now
        db.session.add(attempt)
        db.session.flush()

        window = current_app.config.get('BRUTE_FORCE_WINDOW_MINUTES', 15)
        threshold = current_app.config.get('BRUTE_FORCE_MAX_ATTEMPTS', 5)
        window_start = now - timedelta(minutes=window)

        count = db.session.query(db.LoginAttempt).filter(
            db.LoginAttempt.ipAddress == ip,
            db.LoginAttempt.attemptedAt >= window_start,
        ).count()

        if count >= threshold:
            minutes = _ban_minutes_for(ip)
            ban = db.BannedIp()
            ban.ipAddress = ip
            ban.bannedAt = now
            ban.expiresAt = now + timedelta(minutes=minutes)
            ban.reason = "admin_login"
            ban.failCount = count
            db.session.add(ban)

            db.session.query(db.LoginAttempt).filter(
                db.LoginAttempt.ipAddress == ip
            ).delete(synchronize_session=False)

        _prune_login_attempts()
        db.session.commit()
    except SQLAlchemyError:
        # Without an explicit rollback the pending LoginAttempt insert (or
        # ban write) bleeds into whatever the caller does next on the same
        # request scope. The brute-force check is best-effort; log the
        # failure and let the original request continue.
        db.session.rollback()
        current_app.logger.exception(
            "Failed to record brute-force failure for ip=%s", ip,
        )


def record_success_admin(ip: str) -> None:
    """Successful admin login: clear ``LoginAttempt`` for the IP, expire any
    active ``BannedIp`` rows, and (when ``BRUTE_FORCE_AUTO_TRUST_ADMIN``)
    upsert an ``AdminTrustedIp`` row.

    Historical ``BannedIp`` rows are kept so they still count toward the
    progressive schedule for any future hostile use of the same IP.

    No-op if protection is disabled or *ip* is empty.
    """
    if not current_app.config.get('BRUTE_FORCE_PROTECTION', True):
        return
    if not ip:
        return

    now = utcnow_naive()

    db.session.query(db.LoginAttempt).filter(
        db.LoginAttempt.ipAddress == ip
    ).delete(synchronize_session=False)

    db.session.query(db.BannedIp).filter(
        db.BannedIp.ipAddress == ip,
        db.BannedIp.expiresAt != None,  # noqa: E711
        db.BannedIp.expiresAt > now,
    ).update({db.BannedIp.expiresAt: db.BannedIp.bannedAt},
             synchronize_session=False)

    if current_app.config.get('BRUTE_FORCE_AUTO_TRUST_ADMIN', True):
        existing = db.session.get(db.AdminTrustedIp, ip)
        if existing is None:
            row = db.AdminTrustedIp()
            row.ipAddress = ip
            row.firstSeenAt = now
            row.lastSeenAt = now
            db.session.add(row)
        else:
            existing.lastSeenAt = now

    db.session.commit()


def record_probe(ip: str, reason: str, notes: Optional[str] = None) -> None:
    """Instant-ban path for high-signal events (probe URL, hostile UA).

    Skips ``LoginAttempt`` entirely — these aren't threshold-counted. Uses the
    progressive schedule based on prior ``BannedIp`` rows for the IP.

    No-op if protection is disabled or *ip* is trusted.
    """
    if not current_app.config.get('BRUTE_FORCE_PROTECTION', True):
        return
    if not ip or is_trusted(ip):
        return

    now = utcnow_naive()
    minutes = _ban_minutes_for(ip)
    threshold = current_app.config.get('BRUTE_FORCE_MAX_ATTEMPTS', 5)

    ban = db.BannedIp()
    ban.ipAddress = ip
    ban.bannedAt = now
    ban.expiresAt = now + timedelta(minutes=minutes)
    ban.reason = reason
    ban.failCount = threshold
    if notes is not None:
        ban.notes = notes[:255]
    db.session.add(ban)
    db.session.commit()


def is_probe_url(path: str) -> bool:
    """True if *path* matches any entry in ``BRUTE_FORCE_PROBE_URLS``.

    Match is exact-or-prefix: an entry ``/.env`` matches ``/.env``, ``/.env/``,
    ``/.env.bak``. An entry ``/wp-admin`` matches ``/wp-admin`` and
    ``/wp-admin/anything``.
    """
    if not path:
        return False
    probe_urls = current_app.config.get('BRUTE_FORCE_PROBE_URLS', []) or []
    for entry in probe_urls:
        if not entry:
            continue
        if path == entry:
            return True
        if path.startswith(entry + '/'):
            return True
        if path.startswith(entry) and len(path) > len(entry):
            # /.env matches /.env.bak
            next_char = path[len(entry)]
            if not next_char.isalnum():
                return True
    return False


def is_hostile_ua(user_agent_string: str) -> bool:
    """True if any entry in ``BRUTE_FORCE_HOSTILE_UA_PATTERNS`` is a
    case-insensitive substring of the UA. Empty UA returns False (legitimate
    clients with stripped UAs exist).
    """
    if not user_agent_string:
        return False
    patterns = current_app.config.get('BRUTE_FORCE_HOSTILE_UA_PATTERNS', []) or []
    ua_lower = user_agent_string.lower()
    for pattern in patterns:
        if pattern and pattern.lower() in ua_lower:
            return True
    return False
