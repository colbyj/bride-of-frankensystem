"""Tier 2 tests for lazy participant creation when PAGE_LIST doesn't start
with a creation route, and for cold-hit safety of the /end route.

Together these remove the long-standing fragilities that PAGE_LIST must
begin with one of {consent, consent_nc, create_participant,
create_participant_nc} and that /end can only be hit with a valid session.
"""

import json
import os

import pytest
import toml
from flask import session


# ---------------------------------------------------------------------------
# Fixtures: BOFS apps whose PAGE_LIST starts with a non-creation route
# ---------------------------------------------------------------------------

SIMPLE_QUESTIONNAIRE = {
    "title": "Demographics",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "answer"},
    ],
}


def _write_common_files(tmp_path):
    """Write the consent.html stub and an empty questionnaires dir."""
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    return q_dir


def _make_app(tmp_path, config_overrides, debug=False):
    """Construct a BOFS app with the given config (merged into a minimal base)."""
    base = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
    }
    base.update(config_overrides)
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(base), encoding="utf-8")

    original_cwd = os.getcwd()
    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=debug)
    ctx = app.app_context()
    ctx.push()
    return app, ctx, original_cwd


def _teardown(app, ctx, original_cwd):
    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


@pytest.fixture
def app_questionnaire_first(tmp_path):
    """PAGE_LIST starts with a questionnaire route — the canonical lazy-creation
    trigger. Conditions are configured so the balancer runs."""
    q_dir = _write_common_files(tmp_path)
    (q_dir / "demographics.json").write_text(
        json.dumps(SIMPLE_QUESTIONNAIRE), encoding="utf-8"
    )
    app, ctx, cwd = _make_app(tmp_path, {
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Demographics", "path": "questionnaire/demographics"},
            {"name": "End", "path": "end"},
        ],
    })
    yield app
    _teardown(app, ctx, cwd)


@pytest.fixture
def app_consent_first(tmp_path):
    """Baseline: PAGE_LIST starts with consent. Lazy creation MUST NOT fire."""
    _write_common_files(tmp_path)
    app, ctx, cwd = _make_app(tmp_path, {
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "End", "path": "end"},
        ],
    })
    yield app
    _teardown(app, ctx, cwd)


@pytest.fixture
def app_end_first(tmp_path):
    """PAGE_LIST = [end]. /end becomes a freestanding terminus — cold hits
    must render the page without creating a participant."""
    _write_common_files(tmp_path)
    app, ctx, cwd = _make_app(tmp_path, {
        "PAGE_LIST": [
            {"name": "End", "path": "end"},
        ],
    })
    yield app
    _teardown(app, ctx, cwd)


@pytest.fixture
def app_questionnaire_first_debug(tmp_path):
    """Same as app_questionnaire_first but with debug=True so the
    use_debug_picker branch fires."""
    q_dir = _write_common_files(tmp_path)
    (q_dir / "demographics.json").write_text(
        json.dumps(SIMPLE_QUESTIONNAIRE), encoding="utf-8"
    )
    app, ctx, cwd = _make_app(tmp_path, {
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Demographics", "path": "questionnaire/demographics"},
            {"name": "End", "path": "end"},
        ],
    }, debug=True)
    yield app
    _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# Part 1 — Lazy participant creation
# ---------------------------------------------------------------------------

class TestLazyParticipantCreation:

    def test_cold_hit_creates_participant(self, app_questionnaire_first):
        """Cold GET on the first PAGE_LIST entry (a questionnaire) must
        create a Participant row, assign a condition, and set session keys."""
        app = app_questionnaire_first
        client = app.test_client()

        response = client.get("/questionnaire/demographics")

        # The questionnaire renders (no crash, no redirect to /).
        assert response.status_code == 200

        # Exactly one Participant exists, with an assigned condition.
        participants = app.db.session.query(app.db.Participant).all()
        assert len(participants) == 1
        p = participants[0]
        assert p.condition in (1, 2)
        assert p.timeStarted is not None

        # Session reflects the new participant.
        with client.session_transaction() as sess:
            assert sess.get("participantID") == p.participantID
            assert sess.get("condition") in (1, 2)
            assert sess.get("currentUrl") == "questionnaire/demographics"

    def test_consent_first_does_not_lazy_create(self, app_consent_first):
        """When the first PAGE_LIST entry IS a creation route, lazy creation
        must NOT fire — a cold GET on /consent shows the form and waits for
        POST. No Participant row exists until the user submits consent."""
        app = app_consent_first
        client = app.test_client()

        response = client.get("/consent")

        assert response.status_code == 200
        # No participant row should exist yet — /consent's POST is what creates it.
        assert app.db.session.query(app.db.Participant).count() == 0
        with client.session_transaction() as sess:
            assert "participantID" not in sess

    def test_returning_participant_is_noop(self, app_questionnaire_first):
        """A second request from the same session must NOT create a second
        Participant — the predicate ('participantID' not in session) gates
        creation to the first request."""
        app = app_questionnaire_first
        client = app.test_client()

        client.get("/questionnaire/demographics")
        assert app.db.session.query(app.db.Participant).count() == 1

        client.get("/questionnaire/demographics")
        assert app.db.session.query(app.db.Participant).count() == 1

    def test_all_conditions_disabled_redirects_to_quota_full(self, app_questionnaire_first):
        """The same study_closed guard the creation routes use must apply to
        lazy creation: flip every condition to disabled, then a cold GET on
        the first page redirects to ``/end/quota_full``. The quota_full
        wire-in replaced the prior 503 ``study_closed.html`` response so
        admins get a Participant row (with ``end_reason = "quota_full"``)
        for every blocked arrival."""
        app = app_questionnaire_first
        for cond in app.config["CONDITIONS"]:
            cond["enabled"] = False

        client = app.test_client()
        response = client.get(
            "/questionnaire/demographics", follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/end/quota_full")
        # A minimal Participant exists, stamped with end_reason="quota_full"
        # and excluded from balancer counts.
        participants = app.db.session.query(app.db.Participant).all()
        assert len(participants) == 1
        assert participants[0].end_reason == "quota_full"
        assert participants[0].excludeFromCount is True

    def test_debug_picker_redirect(self, app_questionnaire_first_debug):
        """In debug mode with conditions defined, lazy creation must redirect
        to /debug_pick_condition (same as /consent and /create_participant)."""
        app = app_questionnaire_first_debug
        client = app.test_client()

        response = client.get("/questionnaire/demographics",
                              follow_redirects=False)

        # 302 to /debug_pick_condition.
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/debug_pick_condition")
        # Participant was created, but condition is deferred (set to 0 by
        # provide_consent when use_debug_picker is true).
        participants = app.db.session.query(app.db.Participant).all()
        assert len(participants) == 1
        assert participants[0].condition == 0

    def test_condition_lookup_miss_returns_404(self, tmp_path):
        """Lazy creation must surface CONDITIONS_FROM_CSV lookup misses the
        same way the existing creation routes do."""
        q_dir = _write_common_files(tmp_path)
        (q_dir / "demographics.json").write_text(
            json.dumps(SIMPLE_QUESTIONNAIRE), encoding="utf-8"
        )
        # Map exactly one ID — the participant won't match it.
        csv_path = tmp_path / "lookup.csv"
        csv_path.write_text("id,condition\nknown_user,1\n", encoding="utf-8")

        app, ctx, cwd = _make_app(tmp_path, {
            "CONDITIONS": [
                {"label": "Control", "enabled": True},
                {"label": "Treatment", "enabled": True},
            ],
            "CONDITIONS_FROM_CSV": str(csv_path),
            "PAGE_LIST": [
                {"name": "Demographics", "path": "questionnaire/demographics"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            client = app.test_client()
            # Pass an external_id that is NOT in the CSV. The first request
            # captures external_id to the session and 302s to the
            # query-string-free URL; the follow-up triggers lazy creation,
            # which raises ConditionLookupMiss and renders the 404 page.
            response = client.get(
                "/questionnaire/demographics?external_id=stranger",
                follow_redirects=True,
            )

            assert response.status_code == 404
            assert b"ID Not Recognized" in response.data
            # No participant should have been committed.
            assert app.db.session.query(app.db.Participant).count() == 0
        finally:
            _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# Part 2 — /end safe to hit cold
# ---------------------------------------------------------------------------

class TestEndColdHit:

    def test_end_as_first_page_renders_anonymously(self, app_end_first):
        """PAGE_LIST = [end] + cold GET /end: 200, end.html renders, no
        Participant row is created (end is excluded from lazy creation)."""
        app = app_end_first
        client = app.test_client()

        response = client.get("/end")

        assert response.status_code == 200
        assert b"Thanks for participating" in response.data
        # No participant row should exist — end as a first-page terminus
        # doesn't bootstrap one.
        assert app.db.session.query(app.db.Participant).count() == 0

    def test_end_cold_when_consent_is_first_redirects_to_consent(
            self, app_consent_first):
        """Cold GET /end when PAGE_LIST = [consent, end]: bootstrap sets
        currentUrl=consent, doesn't match the request URL, redirects to
        /consent. /end is never entered. (Preserved behavior — verify the
        decorator-removal didn't accidentally open this up.)"""
        app = app_consent_first
        client = app.test_client()

        response = client.get("/end", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/consent")
        # No stamping happened (no participant exists anyway).
        assert app.db.session.query(app.db.Participant).count() == 0

    def test_in_flow_participant_stamps_finished(self, app_questionnaire_first):
        """A participant who arrived at /end via the legitimate flow gets
        timeEnded set and finished=True — current behavior preserved."""
        app = app_questionnaire_first
        client = app.test_client()

        # Step 1: cold GET on the first page lazy-creates a participant.
        client.get("/questionnaire/demographics")
        # Manually advance currentUrl to "end" so verify_correct_page allows
        # the next GET through (simulates POST-advance from the questionnaire).
        with client.session_transaction() as sess:
            sess["currentUrl"] = "end"

        response = client.get("/end")

        assert response.status_code == 200
        # Participant should now be marked finished.
        p = app.db.session.query(app.db.Participant).one()
        assert p.finished is True
        assert p.timeEnded is not None

    def test_end_with_mismatched_ip_does_not_stamp(self, tmp_path):
        """When SESSION_BIND_TO_IP_PARTICIPANT is on and the request IP
        doesn't match the participant's recorded IP, /end renders but does
        NOT stamp finished — matches the IP-binding guarantee the old
        @verify_session_valid decorator used to provide."""
        _write_common_files(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "BRUTE_FORCE_PROTECTION": True,
            "SESSION_BIND_TO_IP_PARTICIPANT": True,
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            # Manually seed a Participant with an IP that differs from the
            # request IP we'll use below.
            from BOFS.util import utcnow_naive
            p = app.db.Participant()
            p.ipAddress = "10.0.0.1"
            p.userAgent = "test"
            p.condition = 0
            p.finished = False
            p.timeStarted = utcnow_naive()
            app.db.session.add(p)
            app.db.session.commit()
            pid = p.participantID

            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end"

            response = client.get(
                "/end", environ_base={"REMOTE_ADDR": "10.0.0.99"},
            )
            assert response.status_code == 200

            # Stamping was skipped because the IPs mismatched.
            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.finished is False
            assert refreshed.timeEnded is None
        finally:
            _teardown(app, ctx, cwd)

    def test_end_with_matching_ip_stamps(self, tmp_path):
        """Counterpart to the mismatched-IP test: when IPs DO match, stamping
        proceeds normally."""
        _write_common_files(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "BRUTE_FORCE_PROTECTION": True,
            "SESSION_BIND_TO_IP_PARTICIPANT": True,
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            from BOFS.util import utcnow_naive
            p = app.db.Participant()
            p.ipAddress = "10.0.0.1"
            p.userAgent = "test"
            p.condition = 0
            p.finished = False
            p.timeStarted = utcnow_naive()
            app.db.session.add(p)
            app.db.session.commit()
            pid = p.participantID

            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end"

            response = client.get(
                "/end", environ_base={"REMOTE_ADDR": "10.0.0.1"},
            )
            assert response.status_code == 200

            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.finished is True
            assert refreshed.timeEnded is not None
        finally:
            _teardown(app, ctx, cwd)
