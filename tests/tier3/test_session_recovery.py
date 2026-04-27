"""Tier 3 integration tests for route_external_id session recovery logic.

Locks down the behaviour of BOFS/default/views.py:195-269 before refactoring.
All assertions match what the code *currently* does; no production code is
modified.
"""

import datetime
import json
import os

import pytest
import toml

from BOFS.BOFSSession import BOFSSessionInterface
from tests.conftest import create_participant_via_consent, SURVEY_QUESTIONNAIRE_FULL


# ---------------------------------------------------------------------------
# Local fixture — PAGE_LIST that includes external_id so verify_correct_page
# doesn't block the route.
# ---------------------------------------------------------------------------

@pytest.fixture
def bofs_app_with_external_id(tmp_path):
    """
    BOFS app whose PAGE_LIST contains external_id between consent and the
    survey, so verify_correct_page allows the POST to proceed.

    PAGE_LIST: consent → external_id → questionnaire/survey → end
    """
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "survey.json").write_text(
        json.dumps(SURVEY_QUESTIONNAIRE_FULL), encoding="utf-8"
    )
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment Recovery",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "GENERATE_COMPLETION_CODE": True,
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "ID", "path": "external_id"},
            {"name": "Survey", "path": "questionnaire/survey"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_blob(data: dict) -> str:
    """Serialize *data* exactly as BOFS does when persisting a session."""
    return BOFSSessionInterface.serializer.dumps(data)


def _create_past_participant(app, mturk_id, condition=2, finished=False):
    """Insert a Participant row directly into the DB and return it."""
    db = app.db
    p = db.Participant()
    p.mTurkID = mturk_id
    p.condition = condition
    p.finished = finished
    p.ipAddress = "127.0.0.1"
    p.userAgent = "test-agent"
    db.session.add(p)
    db.session.commit()
    return p


def _create_session_store(app, participant, mturk_id, data_dict):
    """Insert a SessionStore row for *participant* with serialised *data_dict*."""
    db = app.db
    ss = db.SessionStore()
    ss.sessionID = f"past-session-{participant.participantID}"
    ss.participantID = participant.participantID
    ss.mTurkID = mturk_id
    ss.data = _make_session_blob(data_dict)
    ss.expiry = datetime.datetime.utcnow() + datetime.timedelta(days=21)
    ss.createdOn = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    db.session.add(ss)
    db.session.commit()
    return ss


def _advance_to_external_id(client, app):
    """
    Create a participant via /consent and advance the session's currentUrl to
    'external_id' so verify_correct_page allows the POST.
    Returns the participantID.
    """
    pid = create_participant_via_consent(client, app)
    # After consent the app advances to external_id (it's next in PAGE_LIST).
    with client.session_transaction() as sess:
        assert sess.get("currentUrl") == "external_id", (
            f"Expected currentUrl='external_id' after consent, got {sess.get('currentUrl')!r}"
        )
    return pid


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSessionRecovery:

    # ------------------------------------------------------------------
    # 1. RETRIEVE_SESSIONS=False → no recovery, immediate redirect
    # ------------------------------------------------------------------
    def test_no_recovery_when_retrieve_sessions_disabled(self, bofs_app_with_external_id):
        """RETRIEVE_SESSIONS=False → redirect to /redirect_from_page without touching past data."""
        app = bofs_app_with_external_id
        app.config["RETRIEVE_SESSIONS"] = False

        client = app.test_client()
        pid = _advance_to_external_id(client, app)

        # Record the current participant's condition before the POST
        current_p = app.db.session.query(app.db.Participant).get(pid)
        original_condition = current_p.condition

        mturk_id = "WORKER_DISABLED"
        past_p = _create_past_participant(app, mturk_id, condition=2, finished=True)
        _create_session_store(app, past_p, mturk_id, {
            "condition": 2,
            "currentUrl": "questionnaire/survey",
            "participantID": past_p.participantID,
        })

        response = client.post("/external_id", data={"mTurkID": mturk_id}, follow_redirects=False)

        assert response.status_code == 302
        assert "/redirect_from_page" in response.location

        # Condition must NOT have been replaced from past data
        app.db.session.expire_all()
        current_p = app.db.session.query(app.db.Participant).get(pid)
        assert current_p.condition == original_condition

    # ------------------------------------------------------------------
    # 2. RETRIEVE_SESSIONS=True, ALLOW_RETAKES=False → restore finished past session
    # ------------------------------------------------------------------
    def test_recovery_with_disabled_retakes_restores_session(self, bofs_app_with_external_id):
        """
        ALLOW_RETAKES=False (default): a finished past attempt IS restored because
        ALLOW_RETAKES=False means "don't filter on finished" — the code only adds
        the finished filter when ALLOW_RETAKES=True.
        """
        app = bofs_app_with_external_id
        # Defaults: RETRIEVE_SESSIONS=True, ALLOW_RETAKES=False

        client = app.test_client()
        pid = _advance_to_external_id(client, app)

        mturk_id = "WORKER_RESTORE"
        past_p = _create_past_participant(app, mturk_id, condition=2, finished=True)
        _create_session_store(app, past_p, mturk_id, {
            "condition": 2,
            "currentUrl": "questionnaire/survey",
            "participantID": past_p.participantID,
        })

        response = client.post("/external_id", data={"mTurkID": mturk_id}, follow_redirects=False)

        assert response.status_code == 302
        # Should redirect to the restored currentUrl, not to redirect_from_page
        assert "questionnaire/survey" in response.location

        with client.session_transaction() as sess:
            assert sess.get("condition") == 2

        app.db.session.expire_all()
        current_p = app.db.session.query(app.db.Participant).get(pid)
        # Route sets p.condition = None on recovery
        assert current_p.condition is None

    # ------------------------------------------------------------------
    # 3. ALLOW_RETAKES=True, past attempt finished → skip restoration
    # ------------------------------------------------------------------
    def test_retakes_skips_finished_past_attempt(self, bofs_app_with_external_id):
        """
        ALLOW_RETAKES=True filters OUT finished past attempts — so a finished
        past attempt does NOT get restored.
        """
        app = bofs_app_with_external_id
        app.config["ALLOW_RETAKES"] = True

        client = app.test_client()
        pid = _advance_to_external_id(client, app)

        current_p = app.db.session.query(app.db.Participant).get(pid)
        original_condition = current_p.condition

        mturk_id = "WORKER_RETAKE_FINISHED"
        past_p = _create_past_participant(app, mturk_id, condition=2, finished=True)
        _create_session_store(app, past_p, mturk_id, {
            "condition": 2,
            "currentUrl": "questionnaire/survey",
            "participantID": past_p.participantID,
        })

        response = client.post("/external_id", data={"mTurkID": mturk_id}, follow_redirects=False)

        assert response.status_code == 302
        assert "/redirect_from_page" in response.location

        # Condition must NOT have been replaced
        app.db.session.expire_all()
        current_p = app.db.session.query(app.db.Participant).get(pid)
        assert current_p.condition == original_condition

    # ------------------------------------------------------------------
    # 4. ALLOW_RETAKES=True, past attempt in-progress → restore session
    # ------------------------------------------------------------------
    def test_retakes_restores_in_progress_past_attempt(self, bofs_app_with_external_id):
        """
        ALLOW_RETAKES=True with an unfinished past attempt → session IS restored
        and redirect goes to the past currentUrl.
        """
        app = bofs_app_with_external_id
        app.config["ALLOW_RETAKES"] = True

        client = app.test_client()
        pid = _advance_to_external_id(client, app)

        mturk_id = "WORKER_RETAKE_INPROGRESS"
        past_p = _create_past_participant(app, mturk_id, condition=2, finished=False)
        _create_session_store(app, past_p, mturk_id, {
            "condition": 2,
            "currentUrl": "questionnaire/survey",
            "participantID": past_p.participantID,
        })

        response = client.post("/external_id", data={"mTurkID": mturk_id}, follow_redirects=False)

        assert response.status_code == 302
        assert "questionnaire/survey" in response.location

        with client.session_transaction() as sess:
            assert sess.get("condition") == 2

        app.db.session.expire_all()
        current_p = app.db.session.query(app.db.Participant).get(pid)
        assert current_p.condition is None

    # ------------------------------------------------------------------
    # 5. Loop prevention — currentUrl in blocked set → redirect_from_page
    # ------------------------------------------------------------------
    def test_loop_prevention(self, bofs_app_with_external_id):
        """
        Past session's currentUrl is 'consent' (in the blocked set) → the route
        must NOT redirect there; it falls through to /redirect_from_page.
        """
        app = bofs_app_with_external_id

        client = app.test_client()
        pid = _advance_to_external_id(client, app)

        mturk_id = "WORKER_LOOP"
        past_p = _create_past_participant(app, mturk_id, condition=2, finished=False)
        _create_session_store(app, past_p, mturk_id, {
            "condition": 2,
            "currentUrl": "consent",   # blocked — would cause a loop
            "participantID": past_p.participantID,
        })

        response = client.post("/external_id", data={"mTurkID": mturk_id}, follow_redirects=False)

        assert response.status_code == 302
        assert "/redirect_from_page" in response.location
        assert "consent" not in response.location

    # ------------------------------------------------------------------
    # 6. Condition restored from matching past attempt
    # ------------------------------------------------------------------
    def test_condition_restored_from_matching_past_attempt(self, bofs_app_with_external_id):
        """
        The route iterates pFromMTurkID (the single participant matched by
        sessionFromMTurkID[0].participantID) and overwrites session['condition']
        with any non-zero, non-None condition from that attempt.
        """
        app = bofs_app_with_external_id

        client = app.test_client()
        _advance_to_external_id(client, app)

        mturk_id = "WORKER_CONDITION"
        # Past participant with condition=2 (non-zero, non-None)
        past_p = _create_past_participant(app, mturk_id, condition=2, finished=False)
        _create_session_store(app, past_p, mturk_id, {
            "condition": 2,
            "currentUrl": "questionnaire/survey",
            "participantID": past_p.participantID,
        })

        client.post("/external_id", data={"mTurkID": mturk_id}, follow_redirects=False)

        with client.session_transaction() as sess:
            assert sess.get("condition") == 2

    # ------------------------------------------------------------------
    # 7. form value written to participant
    # ------------------------------------------------------------------
    def test_form_value_written_to_participant(self, bofs_app_with_external_id):
        """POST /external_id writes mTurkID form value to the Participant row."""
        app = bofs_app_with_external_id

        client = app.test_client()
        pid = _advance_to_external_id(client, app)

        client.post("/external_id", data={"mTurkID": "ABC123"}, follow_redirects=False)

        app.db.session.expire_all()
        p = app.db.session.query(app.db.Participant).get(pid)
        assert p.mTurkID == "ABC123"
