"""Tier 2 tests for ParticipantRoutingService.

Exercise the service against a real PageList and Flask session, using the
``bofs_app_with_questionnaires`` fixture (PAGE_LIST: consent →
questionnaire/survey → questionnaire/survey/before → end).
"""

import datetime

import pytest
from flask import session

from BOFS.services.routing import ParticipantRoutingService


def _make_participant(app):
    p = app.db.Participant()
    p.mTurkID = ""
    p.ipAddress = "127.0.0.1"
    p.userAgent = "test-agent"
    p.condition = 0
    p.finished = False
    p.excludeFromCount = False
    p.timeStarted = datetime.datetime.utcnow()
    app.db.session.add(p)
    app.db.session.commit()
    return p


class TestNavigationDelegates:

    def test_next_path_matches_page_list(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent"):
            session["condition"] = 0
            service = ParticipantRoutingService.from_app()
            assert service.next_path("consent") == "questionnaire/survey"
            assert service.next_path("questionnaire/survey") == "questionnaire/survey/before"

    def test_previous_path_matches_page_list(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/questionnaire/survey/before"):
            session["condition"] = 0
            service = ParticipantRoutingService.from_app()
            assert service.previous_path("questionnaire/survey/before") == "questionnaire/survey"

    def test_current_index(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/questionnaire/survey"):
            session["condition"] = 0
            service = ParticipantRoutingService.from_app()
            assert service.current_index("questionnaire/survey") == 1
            assert service.current_index("end") == 3


class TestAdvanceToNext:

    def test_writes_session_and_returns_redirect(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent"):
            session["condition"] = 0
            session["currentUrl"] = "consent"
            response = ParticipantRoutingService.from_app().advance_to_next("consent")

            assert response.status_code == 302
            assert response.location.endswith("/questionnaire/survey")
            assert session["currentUrl"] == "questionnaire/survey"

    def test_closes_outgoing_progress_row(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app)

        # Seed a Progress row in the "open" state
        progress = app.db.Progress()
        progress.participantID = p.participantID
        progress.path = "consent"
        progress.startedOn = datetime.datetime.utcnow()
        app.db.session.add(progress)
        app.db.session.commit()

        with app.test_request_context("/consent"):
            session["participantID"] = p.participantID
            session["condition"] = 0
            session["currentUrl"] = "consent"
            ParticipantRoutingService.from_app().advance_to_next("consent")

        refreshed = app.db.session.query(app.db.Progress).filter_by(
            participantID=p.participantID, path="consent"
        ).one()
        assert refreshed.submittedOn is not None


class TestAdvanceFromRequest:

    def test_uses_url_rule_when_set(self, bofs_app_with_questionnaires):
        """When a researcher's view calls into the service, request.url_rule.rule
        is set to that view's rule and is used as the "from" page."""
        app = bofs_app_with_questionnaires
        with app.test_client() as client:
            # /consent → /redirect_from_page/consent → advance_to_next("consent")
            client.post("/consent", follow_redirects=True)
            with client.session_transaction() as sess:
                assert sess["currentUrl"] == "questionnaire/survey"

    def test_falls_back_to_session_when_self_loop(self, bofs_app_with_questionnaires):
        """Hitting /redirect_next_page directly: url_rule is /redirect_next_page,
        which is a self-loop, so the service falls back to session['currentUrl']."""
        app = bofs_app_with_questionnaires
        with app.test_client() as client:
            client.post("/consent", follow_redirects=True)
            # Now currentUrl == questionnaire/survey
            client.get("/redirect_next_page", follow_redirects=False)
            with client.session_transaction() as sess:
                assert sess["currentUrl"] == "questionnaire/survey/before"

    def test_end_short_circuit(self, bofs_app_with_questionnaires):
        """When the resolved current page is 'end', redirect to /end without
        calling next_path (which would loop on the last entry)."""
        app = bofs_app_with_questionnaires
        with app.test_request_context(
            "/redirect_next_page",
            headers={"Referer": "http://localhost/end"},
        ):
            session["condition"] = 0
            session["currentUrl"] = "end"
            response = ParticipantRoutingService.from_app().advance_from_request()
            assert response.status_code == 302
            assert response.location.endswith("/end")
            # session['currentUrl'] is NOT advanced — end is terminal
            assert session["currentUrl"] == "end"

    def test_missing_session_bounces_home(self, bofs_app_with_questionnaires):
        """A stale request to /redirect_next_page after /restart cleared the
        session bounces to / so verify_correct_page can rebuild the flow."""
        app = bofs_app_with_questionnaires
        with app.test_request_context("/redirect_next_page"):
            session.clear()
            response = ParticipantRoutingService.from_app().advance_from_request()
            assert response.status_code == 302
            assert response.location.endswith("/")


class TestGoToAndGoBack:

    def test_go_to_sets_session(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/redirect_to_page/end"):
            session["condition"] = 0
            response = ParticipantRoutingService.from_app().go_to("end")
            assert response.status_code == 302
            assert response.location.endswith("/end")
            assert session["currentUrl"] == "end"

    def test_go_back_steps_one(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/redirect_previous_page"):
            session["condition"] = 0
            session["currentUrl"] = "questionnaire/survey/before"
            response = ParticipantRoutingService.from_app().go_back()
            assert response.status_code == 302
            assert response.location.endswith("/questionnaire/survey")
            assert session["currentUrl"] == "questionnaire/survey"


class TestVerifyCorrectPageHelpers:

    def test_bootstrap_when_missing(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent"):
            session.clear()
            session["condition"] = 0
            bootstrapped = ParticipantRoutingService.from_app().bootstrap_session_if_needed()
            assert bootstrapped == "consent"
            assert session["currentUrl"] == "consent"

    def test_bootstrap_noop_when_set(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent"):
            session["condition"] = 0
            session["currentUrl"] = "questionnaire/survey"
            bootstrapped = ParticipantRoutingService.from_app().bootstrap_session_if_needed()
            assert bootstrapped is None
            assert session["currentUrl"] == "questionnaire/survey"

    def test_enforce_redirects_on_mismatch(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/end"):
            session["condition"] = 0
            session["currentUrl"] = "questionnaire/survey"
            response = ParticipantRoutingService.from_app().enforce_current_page("end")
            assert response is not None
            assert response.status_code == 302
            assert response.location.endswith("/questionnaire/survey")

    def test_enforce_passes_when_match(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent"):
            session["condition"] = 0
            session["currentUrl"] = "consent"
            assert ParticipantRoutingService.from_app().enforce_current_page("consent") is None

    def test_enforce_passes_when_no_session_url(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent"):
            session.clear()
            assert ParticipantRoutingService.from_app().enforce_current_page("consent") is None


class TestProgressTracking:

    def test_track_progress_creates_row(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app)
        with app.test_request_context("/consent", method="GET"):
            session["participantID"] = p.participantID
            session["condition"] = 0
            ParticipantRoutingService.from_app().track_progress("consent")

        row = app.db.session.query(app.db.Progress).filter_by(
            participantID=p.participantID, path="consent"
        ).one()
        assert row.startedOn is not None
        assert row.submittedOn is None  # GET does not close

    def test_track_progress_post_closes_row(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app)

        # First a GET to create the row
        with app.test_request_context("/questionnaire/survey", method="GET"):
            session["participantID"] = p.participantID
            session["condition"] = 0
            ParticipantRoutingService.from_app().track_progress("questionnaire/survey")

        # Then a POST closes submittedOn
        with app.test_request_context("/questionnaire/survey", method="POST"):
            session["participantID"] = p.participantID
            session["condition"] = 0
            ParticipantRoutingService.from_app().track_progress("questionnaire/survey")

        row = app.db.session.query(app.db.Progress).filter_by(
            participantID=p.participantID, path="questionnaire/survey"
        ).one()
        assert row.submittedOn is not None

    def test_track_progress_noop_without_participant(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        with app.test_request_context("/consent", method="GET"):
            session.clear()
            # Should not raise
            ParticipantRoutingService.from_app().track_progress("consent")

        assert app.db.session.query(app.db.Progress).count() == 0

    def test_close_progress_sets_submitted(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app)
        progress = app.db.Progress()
        progress.participantID = p.participantID
        progress.path = "consent"
        progress.startedOn = datetime.datetime.utcnow()
        app.db.session.add(progress)
        app.db.session.commit()

        with app.test_request_context("/consent"):
            session["participantID"] = p.participantID
            session["condition"] = 0
            ParticipantRoutingService.from_app().close_progress("consent")

        row = app.db.session.query(app.db.Progress).filter_by(
            participantID=p.participantID, path="consent"
        ).one()
        assert row.submittedOn is not None

    def test_close_progress_noop_when_already_closed(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app)
        original = datetime.datetime(2020, 1, 1, 12, 0, 0)
        progress = app.db.Progress()
        progress.participantID = p.participantID
        progress.path = "consent"
        progress.startedOn = original
        progress.submittedOn = original
        app.db.session.add(progress)
        app.db.session.commit()

        with app.test_request_context("/consent"):
            session["participantID"] = p.participantID
            session["condition"] = 0
            ParticipantRoutingService.from_app().close_progress("consent")

        row = app.db.session.query(app.db.Progress).filter_by(
            participantID=p.participantID, path="consent"
        ).one()
        assert row.submittedOn == original
