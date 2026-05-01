"""Tier 2 tests for the brute-force protection service module.

Uses the ``bofs_app`` fixture from conftest.py (in-memory SQLite, app context
pushed). The fixture has ``BRUTE_FORCE_PROTECTION = False`` by default; tests
enable it explicitly.
"""

from datetime import timedelta

import pytest

from BOFS.services import brute_force
from BOFS.util import utcnow_naive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enable_protection(app, **overrides):
    """Turn on brute-force protection with optional config overrides."""
    app.config['BRUTE_FORCE_PROTECTION'] = True
    app.config.update(overrides)


def _make_ban(app, ip, expires_in_minutes=60, reason="admin_login"):
    """Create a BannedIp row directly (bypasses record_*)."""
    now = utcnow_naive()
    ban = app.db.BannedIp()
    ban.ipAddress = ip
    ban.bannedAt = now
    ban.expiresAt = now + timedelta(minutes=expires_in_minutes)
    ban.reason = reason
    ban.failCount = 5
    app.db.session.add(ban)
    app.db.session.commit()
    return ban


# ---------------------------------------------------------------------------
# get_client_ip — IP detection hardening (the spoofing fix)
# ---------------------------------------------------------------------------

class TestGetClientIp:
    def test_returns_remote_addr(self, bofs_app):
        with bofs_app.test_request_context('/', environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            assert brute_force.get_client_ip() == '10.0.0.1'

    def test_ignores_x_real_ip_without_proxyfix(self, bofs_app):
        """Without BEHIND_REVERSE_PROXY = true, X-Real-IP is spoofable and
        must not be trusted. This is the core of the IP-detection hardening."""
        with bofs_app.test_request_context(
                '/',
                environ_base={'REMOTE_ADDR': '127.0.0.1'},
                headers={'X-Real-IP': '1.2.3.4'}):
            assert brute_force.get_client_ip() == '127.0.0.1'

    def test_ignores_x_forwarded_for_without_proxyfix(self, bofs_app):
        with bofs_app.test_request_context(
                '/',
                environ_base={'REMOTE_ADDR': '127.0.0.1'},
                headers={'X-Forwarded-For': '1.2.3.4'}):
            assert brute_force.get_client_ip() == '127.0.0.1'


# ---------------------------------------------------------------------------
# is_trusted
# ---------------------------------------------------------------------------

class TestIsTrusted:
    def test_static_trusted_ips(self, bofs_app):
        bofs_app.config['TRUSTED_IPS'] = ['10.0.0.5']
        with bofs_app.test_request_context('/'):
            assert brute_force.is_trusted('10.0.0.5') is True
            assert brute_force.is_trusted('10.0.0.6') is False

    def test_admin_trusted_table(self, bofs_app):
        row = bofs_app.db.AdminTrustedIp()
        row.ipAddress = '10.0.0.7'
        bofs_app.db.session.add(row)
        bofs_app.db.session.commit()
        with bofs_app.test_request_context('/'):
            assert brute_force.is_trusted('10.0.0.7') is True

    def test_empty_ip_not_trusted(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_trusted('') is False


# ---------------------------------------------------------------------------
# is_banned
# ---------------------------------------------------------------------------

class TestIsBanned:
    def test_unbanned_ip(self, bofs_app):
        _enable_protection(bofs_app)
        with bofs_app.test_request_context('/'):
            assert brute_force.is_banned('10.0.0.1') is False

    def test_active_ban(self, bofs_app):
        _enable_protection(bofs_app)
        _make_ban(bofs_app, '10.0.0.1')
        with bofs_app.test_request_context('/'):
            assert brute_force.is_banned('10.0.0.1') is True

    def test_expired_ban(self, bofs_app):
        _enable_protection(bofs_app)
        _make_ban(bofs_app, '10.0.0.1', expires_in_minutes=-1)
        with bofs_app.test_request_context('/'):
            assert brute_force.is_banned('10.0.0.1') is False

    def test_protection_disabled(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = False
        _make_ban(bofs_app, '10.0.0.1')
        with bofs_app.test_request_context('/'):
            assert brute_force.is_banned('10.0.0.1') is False

    def test_trusted_ip_not_banned(self, bofs_app):
        _enable_protection(bofs_app, TRUSTED_IPS=['10.0.0.1'])
        _make_ban(bofs_app, '10.0.0.1')
        with bofs_app.test_request_context('/'):
            assert brute_force.is_banned('10.0.0.1') is False


class TestSecondsUntilUnban:
    def test_returns_remaining_seconds(self, bofs_app):
        _enable_protection(bofs_app)
        _make_ban(bofs_app, '10.0.0.1', expires_in_minutes=10)
        with bofs_app.test_request_context('/'):
            seconds = brute_force.seconds_until_unban('10.0.0.1')
        # Allow a small fudge for clock drift between rows being inserted
        assert 595 <= seconds <= 600

    def test_no_ban_returns_default(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.seconds_until_unban('10.0.0.1') == 60


# ---------------------------------------------------------------------------
# record_failure
# ---------------------------------------------------------------------------

class TestRecordFailure:
    def test_below_threshold_no_ban(self, bofs_app):
        _enable_protection(bofs_app, BRUTE_FORCE_MAX_ATTEMPTS=5)
        with bofs_app.test_request_context('/'):
            for _ in range(4):
                brute_force.record_failure('10.0.0.1')
        # 4 attempts, no ban
        ban_count = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').count()
        assert ban_count == 0
        attempt_count = bofs_app.db.session.query(bofs_app.db.LoginAttempt).filter_by(
            ipAddress='10.0.0.1').count()
        assert attempt_count == 4

    def test_at_threshold_triggers_ban(self, bofs_app):
        _enable_protection(bofs_app, BRUTE_FORCE_MAX_ATTEMPTS=5)
        with bofs_app.test_request_context('/'):
            for _ in range(5):
                brute_force.record_failure('10.0.0.1')
        # Ban created, LoginAttempt rows for the IP cleared
        ban_count = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').count()
        assert ban_count == 1
        attempt_count = bofs_app.db.session.query(bofs_app.db.LoginAttempt).filter_by(
            ipAddress='10.0.0.1').count()
        assert attempt_count == 0

    def test_protection_disabled_noop(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = False
        with bofs_app.test_request_context('/'):
            for _ in range(10):
                brute_force.record_failure('10.0.0.1')
        ban_count = bofs_app.db.session.query(bofs_app.db.BannedIp).count()
        attempt_count = bofs_app.db.session.query(bofs_app.db.LoginAttempt).count()
        assert ban_count == 0
        assert attempt_count == 0

    def test_trusted_ip_noop(self, bofs_app):
        _enable_protection(bofs_app, BRUTE_FORCE_MAX_ATTEMPTS=2,
                           TRUSTED_IPS=['10.0.0.1'])
        with bofs_app.test_request_context('/'):
            for _ in range(10):
                brute_force.record_failure('10.0.0.1')
        ban_count = bofs_app.db.session.query(bofs_app.db.BannedIp).count()
        assert ban_count == 0


class TestProgressiveSchedule:
    def test_first_ban_uses_first_slot(self, bofs_app):
        _enable_protection(bofs_app,
                           BRUTE_FORCE_MAX_ATTEMPTS=2,
                           BRUTE_FORCE_BAN_SCHEDULE=[1, 5, 60])
        with bofs_app.test_request_context('/'):
            for _ in range(2):
                brute_force.record_failure('10.0.0.1')
        ban = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').first()
        assert ban is not None
        delta = (ban.expiresAt - ban.bannedAt).total_seconds()
        assert delta == pytest.approx(60, abs=2)  # 1 minute = 60 seconds

    def test_second_ban_uses_second_slot(self, bofs_app):
        _enable_protection(bofs_app,
                           BRUTE_FORCE_MAX_ATTEMPTS=2,
                           BRUTE_FORCE_BAN_SCHEDULE=[1, 5, 60])
        with bofs_app.test_request_context('/'):
            # First ban
            for _ in range(2):
                brute_force.record_failure('10.0.0.1')
            # Expire it manually so we can trigger a 2nd one without time
            existing = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
                ipAddress='10.0.0.1').first()
            existing.expiresAt = existing.bannedAt
            bofs_app.db.session.commit()
            # Second ban
            for _ in range(2):
                brute_force.record_failure('10.0.0.1')
        bans = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').order_by(bofs_app.db.BannedIp.id).all()
        assert len(bans) == 2
        delta_2 = (bans[1].expiresAt - bans[1].bannedAt).total_seconds()
        assert delta_2 == pytest.approx(300, abs=2)  # 5 minutes = 300 seconds

    def test_final_slot_sticks(self, bofs_app):
        _enable_protection(bofs_app,
                           BRUTE_FORCE_MAX_ATTEMPTS=2,
                           BRUTE_FORCE_BAN_SCHEDULE=[1, 5])
        # Pre-seed 5 historical bans so the next one indexes past the schedule
        for _ in range(5):
            _make_ban(bofs_app, '10.0.0.1', expires_in_minutes=-1)
        with bofs_app.test_request_context('/'):
            for _ in range(2):
                brute_force.record_failure('10.0.0.1')
        bans = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').order_by(bofs_app.db.BannedIp.id).all()
        # 5 historical + 1 new = 6
        assert len(bans) == 6
        delta = (bans[-1].expiresAt - bans[-1].bannedAt).total_seconds()
        assert delta == pytest.approx(300, abs=2)  # final slot is 5 minutes


# ---------------------------------------------------------------------------
# record_success_admin
# ---------------------------------------------------------------------------

class TestRecordSuccessAdmin:
    def test_clears_login_attempts(self, bofs_app):
        _enable_protection(bofs_app)
        with bofs_app.test_request_context('/'):
            brute_force.record_failure('10.0.0.1')
            brute_force.record_failure('10.0.0.1')
            brute_force.record_success_admin('10.0.0.1')
        attempts = bofs_app.db.session.query(bofs_app.db.LoginAttempt).filter_by(
            ipAddress='10.0.0.1').count()
        assert attempts == 0

    def test_expires_active_ban(self, bofs_app):
        _enable_protection(bofs_app)
        ban = _make_ban(bofs_app, '10.0.0.1', expires_in_minutes=60)
        original_banned_at = ban.bannedAt
        with bofs_app.test_request_context('/'):
            brute_force.record_success_admin('10.0.0.1')
        # Ban row still exists (kept for progressive schedule history)
        # but expiresAt is now <= bannedAt
        bofs_app.db.session.refresh(ban)
        assert ban.expiresAt <= ban.bannedAt
        assert ban.bannedAt == original_banned_at  # history preserved

    def test_inserts_admin_trusted_ip(self, bofs_app):
        _enable_protection(bofs_app)
        with bofs_app.test_request_context('/'):
            brute_force.record_success_admin('10.0.0.1')
        row = bofs_app.db.session.get(bofs_app.db.AdminTrustedIp, '10.0.0.1')
        assert row is not None
        assert row.firstSeenAt is not None
        assert row.lastSeenAt is not None

    def test_refreshes_last_seen(self, bofs_app):
        _enable_protection(bofs_app)
        with bofs_app.test_request_context('/'):
            brute_force.record_success_admin('10.0.0.1')
            row = bofs_app.db.session.get(bofs_app.db.AdminTrustedIp, '10.0.0.1')
            first_seen = row.firstSeenAt
            initial_last_seen = row.lastSeenAt
            # Second call after a moment
            import time
            time.sleep(0.01)
            brute_force.record_success_admin('10.0.0.1')
            bofs_app.db.session.refresh(row)
        assert row.firstSeenAt == first_seen
        assert row.lastSeenAt > initial_last_seen

    def test_auto_trust_disabled(self, bofs_app):
        _enable_protection(bofs_app, BRUTE_FORCE_AUTO_TRUST_ADMIN=False)
        ban = _make_ban(bofs_app, '10.0.0.1', expires_in_minutes=60)
        with bofs_app.test_request_context('/'):
            brute_force.record_failure('10.0.0.1')
            brute_force.record_success_admin('10.0.0.1')
        # Ban still expired and attempts cleared
        bofs_app.db.session.refresh(ban)
        assert ban.expiresAt <= ban.bannedAt
        attempts = bofs_app.db.session.query(bofs_app.db.LoginAttempt).count()
        assert attempts == 0
        # But no AdminTrustedIp row
        row = bofs_app.db.session.get(bofs_app.db.AdminTrustedIp, '10.0.0.1')
        assert row is None

    def test_protection_disabled_noop(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = False
        with bofs_app.test_request_context('/'):
            brute_force.record_success_admin('10.0.0.1')
        row = bofs_app.db.session.get(bofs_app.db.AdminTrustedIp, '10.0.0.1')
        assert row is None


# ---------------------------------------------------------------------------
# record_probe (instant-ban path)
# ---------------------------------------------------------------------------

class TestRecordProbe:
    def test_instant_ban(self, bofs_app):
        _enable_protection(bofs_app)
        with bofs_app.test_request_context('/'):
            brute_force.record_probe('10.0.0.1', 'probe_url', notes='/.env')
        ban = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').first()
        assert ban is not None
        assert ban.reason == 'probe_url'
        assert ban.notes == '/.env'

    def test_skips_login_attempt(self, bofs_app):
        _enable_protection(bofs_app)
        with bofs_app.test_request_context('/'):
            brute_force.record_probe('10.0.0.1', 'probe_url')
        attempts = bofs_app.db.session.query(bofs_app.db.LoginAttempt).count()
        assert attempts == 0

    def test_trusted_ip_noop(self, bofs_app):
        _enable_protection(bofs_app, TRUSTED_IPS=['10.0.0.1'])
        with bofs_app.test_request_context('/'):
            brute_force.record_probe('10.0.0.1', 'probe_url')
        ban_count = bofs_app.db.session.query(bofs_app.db.BannedIp).count()
        assert ban_count == 0

    def test_protection_disabled_noop(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = False
        with bofs_app.test_request_context('/'):
            brute_force.record_probe('10.0.0.1', 'probe_url')
        ban_count = bofs_app.db.session.query(bofs_app.db.BannedIp).count()
        assert ban_count == 0

    def test_uses_progressive_schedule(self, bofs_app):
        _enable_protection(bofs_app, BRUTE_FORCE_BAN_SCHEDULE=[1, 5])
        with bofs_app.test_request_context('/'):
            brute_force.record_probe('10.0.0.1', 'probe_url')
            brute_force.record_probe('10.0.0.1', 'probe_url')
        bans = bofs_app.db.session.query(bofs_app.db.BannedIp).filter_by(
            ipAddress='10.0.0.1').order_by(bofs_app.db.BannedIp.id).all()
        assert len(bans) == 2
        delta_1 = (bans[0].expiresAt - bans[0].bannedAt).total_seconds()
        delta_2 = (bans[1].expiresAt - bans[1].bannedAt).total_seconds()
        assert delta_1 == pytest.approx(60, abs=2)
        assert delta_2 == pytest.approx(300, abs=2)

    def test_notes_truncated(self, bofs_app):
        _enable_protection(bofs_app)
        long_notes = 'A' * 500
        with bofs_app.test_request_context('/'):
            brute_force.record_probe('10.0.0.1', 'hostile_ua', notes=long_notes)
        ban = bofs_app.db.session.query(bofs_app.db.BannedIp).first()
        assert len(ban.notes) == 255


# ---------------------------------------------------------------------------
# is_probe_url
# ---------------------------------------------------------------------------

class TestIsProbeUrl:
    @pytest.fixture(autouse=True)
    def _setup(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROBE_URLS'] = [
            '/.env', '/wp-admin', '/.git', '/phpmyadmin'
        ]

    def test_exact_match(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_probe_url('/.env') is True

    def test_extension_match(self, bofs_app):
        """`/.env` should match `/.env.bak` (probes for env file backups)."""
        with bofs_app.test_request_context('/'):
            assert brute_force.is_probe_url('/.env.bak') is True

    def test_subpath_match(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_probe_url('/wp-admin/something') is True
            assert brute_force.is_probe_url('/.git/config') is True

    def test_legitimate_paths_dont_match(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_probe_url('/') is False
            assert brute_force.is_probe_url('/consent') is False
            assert brute_force.is_probe_url('/favicon.ico') is False
            assert brute_force.is_probe_url('/.well-known/security.txt') is False
            assert brute_force.is_probe_url('/robots.txt') is False

    def test_empty_path(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_probe_url('') is False

    def test_no_partial_word_match(self, bofs_app):
        """`/wp-admin` should not match `/wp-admins` or `/wp-administrator-tools`
        — only sub-path or exact match. (Prefix match must be followed by a
        non-alphanumeric boundary.)"""
        with bofs_app.test_request_context('/'):
            assert brute_force.is_probe_url('/wp-administrator') is False


# ---------------------------------------------------------------------------
# is_hostile_ua
# ---------------------------------------------------------------------------

class TestIsHostileUa:
    @pytest.fixture(autouse=True)
    def _setup(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_HOSTILE_UA_PATTERNS'] = [
            'sqlmap', 'nikto', 'nmap'
        ]

    def test_exact_substring(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_hostile_ua('sqlmap/1.5') is True

    def test_substring_with_other_content(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_hostile_ua('Mozilla/5.0 nikto') is True

    def test_case_insensitive(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_hostile_ua('SQLMAP/1.0') is True
            assert brute_force.is_hostile_ua('SqlMap') is True

    def test_empty_ua(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_hostile_ua('') is False

    def test_none_ua(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_hostile_ua(None) is False

    def test_legitimate_browser(self, bofs_app):
        with bofs_app.test_request_context('/'):
            assert brute_force.is_hostile_ua(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            ) is False
