Sessions and Participant State
==============================

Web frameworks use *sessions* to remember who a user is across requests. BOFS uses sessions to track each participant's place in ``PAGE_LIST``, their assigned condition, the external ID they arrived with, and a few other fields. This page covers what's in a session, how it's created and torn down, and the configuration knobs around recovery and IP binding.

Database-backed, not file-based
-------------------------------

Flask's default session implementation stores session data in a signed cookie or in a temporary file on disk. BOFS replaces it with ``BOFSSession``, a database-backed implementation that:

- Persists session state in the project's own database (the same one that holds participant data).
- Survives restarts of the BOFS process — the next request looks the session up by ID and continues.
- Supports the recovery flow used by longitudinal and crowdsourced studies (see below).

The implementation lives in ``BOFS/BOFSSession.py``. You don't interact with it directly — Flask's standard ``session`` proxy works the same way it always does.

What's in a session
-------------------

Six fields cover the participant lifecycle. Each is populated as the participant moves through ``PAGE_LIST``:

- ``session['participantID']`` — the database PK of the current participant. Set when the participant row is created (on consent or on a ``create_participant`` route).
- ``session['condition']`` — the assigned condition number (1+, or 0 if no condition has been assigned). Set at the same time as ``participantID`` for ``consent`` and ``create_participant``; later for the ``_nc`` variants if and when the participant hits ``assign_condition``.
- ``session['currentUrl']`` — the page the participant should be on according to ``PAGE_LIST``. Updated on every page navigation.
- ``session['externalID']`` — the external ID, regardless of source. Captured from URL parameters (``PROLIFIC_PID``, ``external_id``) on the consent page, or set on the manual ``external_id`` page. Also available as ``session['mTurkID']`` — both keys are kept in sync at every BOFS write site for backward compatibility with code written before the rename.
- ``session['source']`` — the recruitment channel, set from a ``?source=`` URL parameter. Inferred as ``"prolific"`` when ``PROLIFIC_PID`` is present and no explicit source is given. Free-form string; expression code (``show_if = "source == 'prolific'"``) can branch on it. Absent when the participant arrived without any source hint — treat ``None`` as "unknown source," not as a specific value.
- ``session['code']`` — the completion code, set near the end of the experiment when ``GENERATE_COMPLETION_CODE = true``.

Admin sessions also exist (a separate session row marking an authenticated admin) but don't share these fields — they're orthogonal to participant sessions.

Lifecycle
---------

The session is created on the first POST to a participant-creation route — ``consent``, ``consent_nc``, ``create_participant``, or ``create_participant_nc``. Before that, a participant browsing the consent page has only an unauthenticated session row with no ``participantID``.

After creation, every page navigation:

1. Reads the session from the database via the cookie's session ID.
2. Compares ``session['currentUrl']`` against the URL being requested. ``@verify_correct_page`` redirects to ``currentUrl`` if they don't match.
3. Updates ``session['currentUrl']`` after a successful submission, advancing to the next entry in ``PAGE_LIST`` (with conditional routing and ``show_if`` applied).

The session ends in one of three ways:

- The participant reaches the ``end`` page; ``session['code']`` is populated and the participant's ``finished`` flag is set.
- ``ABANDONED_MINUTES`` of silence go by without an activity ping; the participant is treated as abandoned. The session row remains in the database but is not counted for condition balancing (unless ``COUNTS_INCLUDE_ABANDONED = true``).
- The participant explicitly visits ``/restart``, which clears the session and routes them back to the first page.

Session recovery
----------------

Two configuration settings control what happens when a participant returns with an external ID that's already been seen.

- ``RETRIEVE_SESSIONS = true`` (default) — when an incoming request carries an external ID (URL parameter or manual entry) that matches an existing participant, BOFS loads that participant's session and resumes from their current page. The participant doesn't see consent again; their condition assignment is preserved.
- ``ALLOW_RETAKES = false`` (default) — a participant whose session is already marked ``finished`` is blocked from starting over. They see a "you've already completed this study" message.

Both default to a configuration appropriate for crowdsourced single-session studies: workers who closed their browser can resume; double submissions are blocked.

For longitudinal studies, the same defaults apply — recovery is what enables day-2 participants to land directly in their day-2 page sequence rather than redo day 1. See :doc:`/building/longitudinal`.

Implementation: the recovery logic lives in ``BOFS/services/session_recovery.py``. The lookup happens at the consent and external-ID routes, before the form is shown.

IP binding
----------

To reduce session-hijacking risk, BOFS binds sessions to the IP they were created on. Two settings control this:

- ``SESSION_BIND_TO_IP_PARTICIPANT = true`` (default) — a participant session is invalidated if a request arrives from a different IP than the one that created it. Set this to ``false`` for studies where participants legitimately switch networks mid-session — for example, mobile users moving between cellular and wifi, where each network change produces a new public IP.
- **Admin sessions are always IP-bound.** There is no opt-out. The trade-off — that an admin moving between networks has to re-authenticate — is accepted because an admin compromise has more impact.

When ``BEHIND_REVERSE_PROXY = true``, BOFS reads the client's real IP from the ``X-Forwarded-For`` header instead of the direct socket connection. Without this, IP binding compares against the reverse proxy's address, which is the same for every client — defeating the binding entirely. See :doc:`/deploying/server` for the deployment context.

Brute-force protection on admin login is built on the same IP infrastructure. See :doc:`/deploying/server` for the brute-force settings (``BRUTE_FORCE_PROTECTION``, ``BRUTE_FORCE_MAX_ATTEMPTS``, etc.).

Recovering from self-lockout
----------------------------

If you (the admin) get locked out — wrong password attempts from your own IP, or a misconfigured ``SESSION_BIND_TO_IP_PARTICIPANT`` after a network change — there are three escapes:

- ``BRUTE_FORCE_AUTO_TRUST_ADMIN = true`` (default) adds successful admin IPs to a persistent allowlist (``admin_trusted_ip`` table) so they're exempted from future bans. If you've ever logged in from this IP successfully, you're in.
- ``TRUSTED_IPS = ["..."]`` is an explicit allowlist that bypasses brute-force protection entirely. Add your office or VPN IP here.
- ``BRUTE_FORCE_PROTECTION = false`` is the kill-switch. Disable it temporarily to log in, then re-enable. Restart BOFS after the change.

For the per-setting reference, see :doc:`/reference/configuration`.

See also
--------

- :doc:`/building/longitudinal` for the longitudinal/multi-session walkthrough that depends on ``RETRIEVE_SESSIONS``.
- :doc:`/deploying/recruiting` for how external IDs from MTurk and Prolific feed into the session.
- :doc:`/deploying/server` for IP binding, brute-force protection, and reverse-proxy configuration.
- :doc:`/reference/configuration` for the full per-setting reference.
