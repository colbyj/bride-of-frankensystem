"""Tier 3 integration tests for navigation enforcement.

Tests redirect routes, verify_correct_page skip prevention,
conditional routing, and external ID capture.
"""

import pytest

from tests.conftest import create_participant_via_consent, submit_questionnaire_data


# ===========================================================================
# Redirect routes
# ===========================================================================

class TestRedirectRoutes:
    def test_redirect_from_page_advances(self, bofs_app_with_questionnaires):
        """/redirect_from_page/consent → currentUrl = questionnaire/survey"""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # After consent, currentUrl should be the page after consent
        with client.session_transaction() as sess:
            assert sess["currentUrl"] == "questionnaire/survey"

    def test_redirect_next_page_advances(self, bofs_app_with_questionnaires):
        """/redirect_next_page → currentUrl advances to next page."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # Currently at questionnaire/survey; hit redirect_next_page
        client.get("/redirect_next_page", follow_redirects=False)

        with client.session_transaction() as sess:
            assert sess["currentUrl"] == "questionnaire/survey/before"

    def test_redirect_previous_page_goes_back(self, bofs_app_with_questionnaires):
        """/redirect_previous_page → currentUrl = previous page."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # Currently at questionnaire/survey; go back
        client.get("/redirect_previous_page", follow_redirects=False)

        with client.session_transaction() as sess:
            assert sess["currentUrl"] == "consent"

    def test_redirect_to_page_jumps(self, bofs_app_with_questionnaires):
        """/redirect_to_page/end → currentUrl = 'end'"""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        response = client.get("/redirect_to_page/end", follow_redirects=False)
        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert sess["currentUrl"] == "end"


# ===========================================================================
# Skip prevention (verify_correct_page)
# ===========================================================================

class TestSkipPrevention:
    def test_skip_ahead_blocked(self, bofs_app_with_questionnaires):
        """currentUrl=questionnaire/survey, GET /end → redirect back."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # Currently at questionnaire/survey, try to jump to /end
        response = client.get("/end", follow_redirects=False)

        assert response.status_code == 302
        assert "questionnaire/survey" in response.location

    def test_go_back_blocked(self, bofs_app_with_questionnaires):
        """currentUrl=end, GET /consent → redirect back to end."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        # Set currentUrl to 'end' via session
        with client.session_transaction() as sess:
            sess["currentUrl"] = "end"

        response = client.get("/consent", follow_redirects=False)

        assert response.status_code == 302
        assert "/end" in response.location

    def test_first_visit_sets_current_url(self, bofs_app_with_questionnaires):
        """No session → currentUrl set to first PAGE_LIST entry ('consent')."""
        app = bofs_app_with_questionnaires
        client = app.test_client()

        # Fresh client, no session
        client.get("/consent")

        with client.session_transaction() as sess:
            assert sess["currentUrl"] == "consent"

    def test_no_session_blocked_from_end(self, bofs_app_with_questionnaires):
        """GET /end without any session → redirect (verify_correct_page)."""
        app = bofs_app_with_questionnaires
        client = app.test_client()

        response = client.get("/end", follow_redirects=False)

        assert response.status_code == 302
        # Redirected to first page (consent), not /end
        assert "consent" in response.location


# ===========================================================================
# External ID capture
# ===========================================================================

class TestExternalIDCapture:
    def test_external_id_captured(self, bofs_app_with_questionnaires):
        """GET with ?external_id=abc → session['mTurkID']='abc'"""
        app = bofs_app_with_questionnaires
        client = app.test_client()

        client.get("/consent?external_id=abc")

        with client.session_transaction() as sess:
            assert sess.get("mTurkID") == "abc"

    def test_prolific_pid_captured(self, bofs_app_with_questionnaires):
        """GET with ?PROLIFIC_PID=xyz → session['mTurkID']='xyz'"""
        app = bofs_app_with_questionnaires
        client = app.test_client()

        client.get("/consent?PROLIFIC_PID=xyz")

        with client.session_transaction() as sess:
            assert sess.get("mTurkID") == "xyz"


# ===========================================================================
# Conditional routing
# ===========================================================================

class TestConditionalRouting:
    def test_condition_1_pages(self, bofs_app_with_conditions):
        """Condition 1 → flat_page_list includes control, not treatment."""
        app = bofs_app_with_conditions

        flat = app.page_list.flat_page_list(condition=1)
        paths = [p["path"] for p in flat]

        assert "questionnaire/control" in paths
        assert "questionnaire/treatment" not in paths

    def test_condition_2_pages(self, bofs_app_with_conditions):
        """Condition 2 → flat_page_list includes treatment, not control."""
        app = bofs_app_with_conditions

        flat = app.page_list.flat_page_list(condition=2)
        paths = [p["path"] for p in flat]

        assert "questionnaire/treatment" in paths
        assert "questionnaire/control" not in paths

    def test_conditional_navigation(self, bofs_app_with_conditions):
        """First participant navigates to the page matching their condition."""
        app = bofs_app_with_conditions
        client = app.test_client()
        create_participant_via_consent(client, app)

        with client.session_transaction() as sess:
            cond = sess["condition"]
            assert cond in (1, 2)
            expected = "questionnaire/control" if cond == 1 else "questionnaire/treatment"
            assert sess["currentUrl"] == expected

    def test_last_page_stays(self, bofs_app_with_questionnaires):
        """At last page, next_path returns same page."""
        app = bofs_app_with_questionnaires

        with app.test_request_context():
            from flask import session
            session["condition"] = 1

            result = app.page_list.next_path("end")
            assert result == "end"
