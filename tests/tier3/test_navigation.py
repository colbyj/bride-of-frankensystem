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


# ===========================================================================
# Page-level show_if — predicates evaluated against stored answers
# ===========================================================================

class TestPageShowIf:
    """Verify a PAGE_LIST entry's ``show_if`` is evaluated against the
    participant's prior questionnaire submissions and skips the page when
    the predicate is false."""

    @pytest.fixture
    def app_with_page_show_if(self, tmp_path):
        import os
        import json
        import toml

        DEMOG = {
            "title": "Demographics",
            "instructions": "",
            "questions": [
                {"questiontype": "num_field", "id": "age",
                 "instructions": "Enter age"},
            ],
        }
        FOLLOWUP = {
            "title": "Followup",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "guardian",
                 "instructions": "Guardian"},
            ],
        }

        q_dir = tmp_path / "questionnaires"
        q_dir.mkdir()
        (q_dir / "demographics.json").write_text(
            json.dumps(DEMOG), encoding="utf-8")
        (q_dir / "followup.json").write_text(
            json.dumps(FOLLOWUP), encoding="utf-8")
        (tmp_path / "consent.html").write_text("<p>Consent</p>",
                                                encoding="utf-8")

        config_data = {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key",
            "TITLE": "Test",
            "ADMIN_PASSWORD": "test",
            "USE_ADMIN": False,
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "Demographics", "path": "questionnaire/demographics"},
                {"name": "Followup", "path": "questionnaire/followup",
                 "show_if": "demographics.age < 18"},
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

    def test_followup_skipped_when_predicate_false(
        self, app_with_page_show_if
    ):
        """A participant who reports age 30 should NOT see the followup."""
        app = app_with_page_show_if
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        # Submit demographics with age 30 (>= 18, so predicate false)
        submit_questionnaire_data(client, "demographics", data_dict={"age": "30"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/followup" not in paths
        assert "questionnaire/demographics" in paths
        assert "end" in paths

    def test_followup_included_when_predicate_true(
        self, app_with_page_show_if
    ):
        """A participant who reports age 14 SHOULD see the followup."""
        app = app_with_page_show_if
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "demographics", data_dict={"age": "14"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/followup" in paths

    def test_followup_visible_before_demographics_submitted(
        self, app_with_page_show_if
    ):
        """When the prior questionnaire hasn't been submitted yet, the
        page should remain visible — the predicate cannot be evaluated,
        so we don't lock the participant out of a path that's still
        being decided."""
        app = app_with_page_show_if
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/followup" in paths

    def test_predicate_does_not_filter_when_no_participant_id(
        self, app_with_page_show_if
    ):
        """Calling flat_page_list without a participant context (e.g. from
        admin or startup) should keep all pages."""
        app = app_with_page_show_if
        # No request context: flat_page_list outside any participant flow.
        flat = app.page_list.flat_page_list(condition=1)
        paths = [p["path"] for p in flat]
        assert "questionnaire/followup" in paths


class TestPageShowIfTags:
    """Verify that page-level ``show_if`` can reference a *specific tagged*
    submission of a questionnaire (``qname.tag.field``) and pick the right
    row when the same questionnaire appears multiple times in PAGE_LIST."""

    @pytest.fixture
    def app_with_tagged_pages(self, tmp_path):
        import os
        import json
        import toml

        SURVEY = {
            "title": "Survey",
            "instructions": "",
            "questions": [
                {"questiontype": "num_field", "id": "rating",
                 "instructions": "Rate"},
            ],
        }

        q_dir = tmp_path / "questionnaires"
        q_dir.mkdir()
        (q_dir / "survey.json").write_text(
            json.dumps(SURVEY), encoding="utf-8")
        (tmp_path / "consent.html").write_text("<p>Consent</p>",
                                                encoding="utf-8")

        # The "improvement_followup" page only fires when the rating in the
        # `before` tagged copy is lower than the rating in the `after` copy.
        config_data = {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key",
            "TITLE": "Test",
            "ADMIN_PASSWORD": "test",
            "USE_ADMIN": False,
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "Before", "path": "questionnaire/survey/before"},
                {"name": "After", "path": "questionnaire/survey/after"},
                {"name": "ImprovementFollowup",
                 "path": "questionnaire/survey/followup",
                 "show_if": "survey.before.rating < survey.after.rating"},
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

    def test_tagged_predicate_resolves_to_specific_rows(
        self, app_with_tagged_pages
    ):
        """before=2, after=4 → predicate true → followup included."""
        app = app_with_tagged_pages
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", tag="before",
                                  data_dict={"rating": "2"})
        submit_questionnaire_data(client, "survey", tag="after",
                                  data_dict={"rating": "4"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/survey/followup" in paths

    def test_tagged_predicate_skips_when_false(
        self, app_with_tagged_pages
    ):
        """before=4, after=2 → predicate false → followup skipped."""
        app = app_with_tagged_pages
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", tag="before",
                                  data_dict={"rating": "4"})
        submit_questionnaire_data(client, "survey", tag="after",
                                  data_dict={"rating": "2"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/survey/followup" not in paths

    def test_tagged_predicate_distinguishes_from_most_recent(
        self, app_with_tagged_pages
    ):
        """If the predicate were just "most recent rating", before=4,
        after=2 (most recent) would yield rating=2. But our predicate is
        ``before.rating < after.rating`` (4 < 2 → false). This guards
        against regressing to the pre-tag behaviour where both refs would
        resolve to whichever submission landed last."""
        app = app_with_tagged_pages
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        # Submit `after` first, then `before` — `before` is most recent
        # by timeEnded. The predicate must still scope each reference to
        # its tag, not pick "most recent regardless of tag".
        submit_questionnaire_data(client, "survey", tag="after",
                                  data_dict={"rating": "5"})
        submit_questionnaire_data(client, "survey", tag="before",
                                  data_dict={"rating": "1"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        # before=1 < after=5 → predicate true → followup included.
        assert "questionnaire/survey/followup" in paths
