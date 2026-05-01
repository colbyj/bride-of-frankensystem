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


class TestPageShowIfCondition:
    """Page-level ``show_if`` can reference the bare reserved name
    ``condition``, which resolves to the participant's assigned condition."""

    @pytest.fixture
    def app_with_condition_show_if(self, tmp_path):
        import os
        import json
        import toml

        SIMPLE = {
            "title": "Simple",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "answer"},
            ],
        }

        q_dir = tmp_path / "questionnaires"
        q_dir.mkdir()
        (q_dir / "control_only.json").write_text(
            json.dumps(SIMPLE), encoding="utf-8")
        (q_dir / "treatment_only.json").write_text(
            json.dumps(SIMPLE), encoding="utf-8")
        (tmp_path / "consent.html").write_text("<p>Consent</p>",
                                                encoding="utf-8")

        config_data = {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key",
            "TITLE": "Test",
            "ADMIN_PASSWORD": "test",
            "USE_ADMIN": False,
            "CONDITIONS": [
                {"label": "Control", "enabled": True},
                {"label": "Treatment", "enabled": True},
            ],
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "ControlOnly",
                 "path": "questionnaire/control_only",
                 "show_if": "condition == 1"},
                {"name": "TreatmentOnly",
                 "path": "questionnaire/treatment_only",
                 "show_if": "condition == 2"},
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

    def test_condition_one_keeps_control_only(self, app_with_condition_show_if):
        app = app_with_condition_show_if

        with app.app_context():
            participant = app.db.Participant()
            participant.condition = 1
            app.db.session.add(participant)
            app.db.session.commit()
            pid = participant.participantID

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/control_only" in paths
        assert "questionnaire/treatment_only" not in paths

    def test_condition_two_keeps_treatment_only(self, app_with_condition_show_if):
        app = app_with_condition_show_if

        with app.app_context():
            participant = app.db.Participant()
            participant.condition = 2
            app.db.session.add(participant)
            app.db.session.commit()
            pid = participant.participantID

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 2
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/treatment_only" in paths
        assert "questionnaire/control_only" not in paths


class TestPageShowIfTableRef:
    """Page-level ``show_if`` can reference a JSONTable export column via
    ``tables.<name>.<column>``; the value is computed per-participant from
    the table's stored rows."""

    @pytest.fixture
    def app_with_table_show_if(self, tmp_path):
        import os
        import json
        import toml

        SIMPLE = {
            "title": "Simple",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "answer"},
            ],
        }

        TRIALS = {
            "columns": {
                "phase": {"default": "practice"},
                "trial_index": {"type": "integer", "default": 0},
                "correct": {"type": "boolean", "default": False},
            },
            "exports": [
                {
                    "filter": "phase = 'practice'",
                    "fields": {
                        "practice_correct": "sum(correct)",
                    },
                },
            ],
        }

        q_dir = tmp_path / "questionnaires"
        q_dir.mkdir()
        (q_dir / "debrief.json").write_text(
            json.dumps(SIMPLE), encoding="utf-8")
        tables_dir = tmp_path / "tables"
        tables_dir.mkdir()
        (tables_dir / "trials.json").write_text(
            json.dumps(TRIALS), encoding="utf-8")
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
                {"name": "Debrief", "path": "questionnaire/debrief",
                 "show_if": "tables.trials.practice_correct < 2"},
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

    def _make_participant(self, app):
        p = app.db.Participant()
        p.condition = 1
        app.db.session.add(p)
        app.db.session.commit()
        return p.participantID

    def _seed_trial(self, app, pid, **fields):
        table_class = app.tables["trials"].db_class
        row = table_class()
        row.participantID = pid
        for k, v in fields.items():
            setattr(row, k, v)
        app.db.session.add(row)
        app.db.session.commit()

    def test_debrief_skipped_when_practice_correct_high(self, app_with_table_show_if):
        app = app_with_table_show_if
        pid = self._make_participant(app)
        # 3 correct trials → practice_correct = 3 → predicate (< 2) false
        self._seed_trial(app, pid, phase="practice", trial_index=1, correct=True)
        self._seed_trial(app, pid, phase="practice", trial_index=2, correct=True)
        self._seed_trial(app, pid, phase="practice", trial_index=3, correct=True)

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/debrief" not in paths

    def test_debrief_kept_when_practice_correct_low(self, app_with_table_show_if):
        app = app_with_table_show_if
        pid = self._make_participant(app)
        # 1 correct trial → practice_correct = 1 → predicate (< 2) true
        self._seed_trial(app, pid, phase="practice", trial_index=1, correct=True)
        self._seed_trial(app, pid, phase="practice", trial_index=2, correct=False)

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/debrief" in paths

    def test_debrief_kept_when_no_data_yet(self, app_with_table_show_if):
        app = app_with_table_show_if
        pid = self._make_participant(app)
        # No rows seeded — the predicate is undecided, so the page stays.

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/debrief" in paths


class TestConditionalRoutingArmShowIf:
    """End-to-end: a participant whose questionnaire answer routes them
    through a ``show_if``-keyed conditional_routing arm."""

    @pytest.fixture
    def app_with_arm_show_if(self, tmp_path):
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
        SIMPLE = {
            "title": "Simple",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "answer"},
            ],
        }

        q_dir = tmp_path / "questionnaires"
        q_dir.mkdir()
        (q_dir / "demographics.json").write_text(
            json.dumps(DEMOG), encoding="utf-8")
        (q_dir / "minor_track.json").write_text(
            json.dumps(SIMPLE), encoding="utf-8")
        (q_dir / "adult_track.json").write_text(
            json.dumps(SIMPLE), encoding="utf-8")
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
                {"conditional_routing": [
                    {"show_if": "demographics.age < 18",
                     "page_list": [
                         {"name": "Minor", "path": "questionnaire/minor_track"},
                     ]},
                    {"show_if": "demographics.age >= 18",
                     "page_list": [
                         {"name": "Adult", "path": "questionnaire/adult_track"},
                     ]},
                ]},
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

    def test_minor_routes_into_minor_arm(self, app_with_arm_show_if):
        app = app_with_arm_show_if
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "demographics",
                                  data_dict={"age": "14"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/minor_track" in paths
        assert "questionnaire/adult_track" not in paths

    def test_adult_routes_into_adult_arm(self, app_with_arm_show_if):
        app = app_with_arm_show_if
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "demographics",
                                  data_dict={"age": "25"})

        with app.test_request_context():
            from flask import session
            session["participantID"] = pid
            session["condition"] = 1
            flat = app.page_list.flat_page_list()
            paths = [p["path"] for p in flat]

        assert "questionnaire/adult_track" in paths
        assert "questionnaire/minor_track" not in paths
