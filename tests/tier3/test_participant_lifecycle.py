"""Tier 3 integration tests for participant lifecycle.

Tests the full happy path through the experiment using Flask test_client:
consent → questionnaire → end, plus progress tracking.
"""

import pytest

from tests.conftest import create_participant_via_consent, submit_questionnaire_data


# ===========================================================================
# Consent
# ===========================================================================

class TestConsent:
    def test_get_consent_renders_page(self, bofs_app_with_questionnaires):
        client = bofs_app_with_questionnaires.test_client()
        response = client.get("/consent")
        assert response.status_code == 200

    def test_post_consent_creates_participant(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        client.post("/consent", follow_redirects=True)

        count = app.db.session.query(app.db.Participant).count()
        assert count == 1

    def test_consent_assigns_condition(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        p = app.db.session.get(app.db.Participant, pid)
        assert p.condition in (1, 2)

    def test_consent_sets_session_vars(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        with client.session_transaction() as sess:
            assert "participantID" in sess
            assert "condition" in sess
            assert "currentUrl" in sess

    def test_consent_redirects_to_next_page(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        response = client.post("/consent", follow_redirects=False)

        assert response.status_code == 302
        assert "/redirect_from_page/consent" in response.location

    def test_consent_honeypot_blocks_bot(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        client.post("/consent", data={"email": "bot@spam.com"}, follow_redirects=True)

        count = app.db.session.query(app.db.Participant).count()
        assert count == 0

    def test_consent_nc_sets_condition_zero(self, bofs_app):
        """POST /consent_nc → condition=0 (requires consent_nc as first page)."""
        from BOFS.PageList import PageList

        bofs_app.page_list = PageList([
            {"name": "Consent", "path": "consent_nc"},
            {"name": "End", "path": "end"},
        ])
        client = bofs_app.test_client()
        client.post("/consent_nc", follow_redirects=True)

        p = bofs_app.db.session.query(bofs_app.db.Participant).first()
        assert p is not None
        assert p.condition == 0


# ===========================================================================
# Questionnaire submission
# ===========================================================================

class TestQuestionnaire:
    def test_questionnaire_get_renders(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # After consent + redirect, currentUrl = questionnaire/survey
        response = client.get("/questionnaire/survey")
        assert response.status_code == 200

    def test_questionnaire_post_saves_data(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Alice", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        q = app.questionnaires["survey"]
        results = q.fetch_all_data()
        assert len(results) == 1
        assert results[0].name == "Alice"
        assert results[0].rating == 4

    def test_questionnaire_sets_timestamps(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Alice", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.timeStarted is not None
        assert result.timeEnded is not None

    def test_questionnaire_sets_participant_id(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Alice", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.participantID == pid


# ===========================================================================
# End page
# ===========================================================================

class TestEnd:
    def _navigate_to_end(self, client, app):
        """Navigate through consent and both questionnaires to reach the end."""
        pid = create_participant_via_consent(client, app)

        # Submit questionnaire/survey (no tag)
        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Alice", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        # Submit questionnaire/survey/before (tag=before)
        submit_questionnaire_data(client, "survey", tag="before", data_dict={
            "name": "Alice", "rating": "5", "age": "31",
            "g1_q1": "4", "g1_q2": "2",
        })

        return pid

    def test_end_marks_finished(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = self._navigate_to_end(client, app)

        response = client.get("/end")
        assert response.status_code == 200

        p = app.db.session.get(app.db.Participant, pid)
        assert p.finished is True
        assert p.timeEnded is not None

    def test_end_shows_code(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        self._navigate_to_end(client, app)

        response = client.get("/end")

        with client.session_transaction() as sess:
            code = sess.get("code")
        assert code is not None
        # The completion code should appear in the rendered HTML
        assert code.encode() in response.data


# ===========================================================================
# Progress tracking
# ===========================================================================

class TestProgress:
    def test_progress_created_on_visit(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        # After consent + redirect, we visited questionnaire/survey
        progress = app.db.session.query(app.db.Progress).filter(
            app.db.Progress.participantID == pid
        ).all()
        paths = [p.path for p in progress]
        assert "questionnaire/survey" in paths

        # startedOn should be set
        q_progress = next(p for p in progress if p.path == "questionnaire/survey")
        assert q_progress.startedOn is not None

    def test_progress_submitted_on_post(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Alice", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        progress = app.db.session.query(app.db.Progress).filter(
            app.db.Progress.participantID == pid,
            app.db.Progress.path == "questionnaire/survey",
        ).one_or_none()

        assert progress is not None
        assert progress.submittedOn is not None


# ===========================================================================
# /restart
# ===========================================================================

class TestRestart:
    def test_clears_session_store_fk_columns(self, bofs_app_with_questionnaires):
        """/restart must null out SessionStore.participantID / .mTurkID so the
        row doesn't keep pointing at the previous participant after a restart.
        Regression: the route used to read request.cookies['session'], but the
        cookie is named per-project (bofs_<hash>), so the lookup was always
        None and the FK columns were never cleared."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        # Sanity: SessionStore row exists and points to our participant.
        cookie_name = app.session_interface.get_cookie_name(app)
        client_cookie = client.get_cookie(cookie_name)
        assert client_cookie is not None, "expected the per-project session cookie"
        ss_before = app.db.session.get(app.db.SessionStore, client_cookie.value)
        assert ss_before is not None
        assert ss_before.participantID == pid

        # /restart must clear the FK columns.
        client.get("/restart", follow_redirects=False)

        # Re-fetch (the row was mutated, not deleted).
        ss_after = app.db.session.get(app.db.SessionStore, client_cookie.value)
        assert ss_after is not None, "SessionStore row should not be deleted"
        assert ss_after.participantID is None, (
            "/restart did not clear SessionStore.participantID — cookie-name lookup is broken"
        )
