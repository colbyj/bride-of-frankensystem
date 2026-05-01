"""Tier 3 integration tests for questionnaire-specific behavior.

Deeper questionnaire tests: tagged instances, resubmission, question types,
radio-grid logging, and calculated fields.
"""

import json
from datetime import datetime

import pytest

from tests.conftest import create_participant_via_consent, submit_questionnaire_data


# ===========================================================================
# Tagging and resubmission
# ===========================================================================

class TestTagging:
    def test_tagged_creates_separate_records(self, bofs_app_with_questionnaires):
        """survey (tag='') and survey/before (tag='before') → 2 DB rows."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # Submit questionnaire/survey (no tag)
        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        # Submit questionnaire/survey/before (tag=before)
        submit_questionnaire_data(client, "survey", tag="before", data_dict={
            "name": "B", "rating": "5", "age": "31",
            "g1_q1": "4", "g1_q2": "2",
        })

        q = app.questionnaires["survey"]
        results = q.fetch_all_data()
        assert len(results) == 2
        tags = {r.tag for r in results}
        assert tags == {"", "before"}

    def test_empty_tag_is_empty_string(self, bofs_app_with_questionnaires):
        """POST without tag → tag='' in DB."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.tag == ""

    def test_resubmit_same_tag_updates(self, bofs_app_with_questionnaires):
        """POST twice with same tag → 1 DB row, updated values."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # First submission
        submit_questionnaire_data(client, "survey", data_dict={
            "name": "First", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        # Navigate back via session to resubmit same questionnaire
        with client.session_transaction() as sess:
            sess["currentUrl"] = "questionnaire/survey"

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Second", "rating": "5", "age": "25",
            "g1_q1": "1", "g1_q2": "2",
        })

        q = app.questionnaires["survey"]
        results = [r for r in q.fetch_all_data() if r.tag == ""]
        assert len(results) == 1
        assert results[0].name == "Second"

    def test_resubmit_preserves_participant_id(self, bofs_app_with_questionnaires):
        """participantID unchanged on resubmit."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        with client.session_transaction() as sess:
            sess["currentUrl"] = "questionnaire/survey"

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "B", "rating": "5", "age": "25",
            "g1_q1": "1", "g1_q2": "2",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.participantID == pid


# ===========================================================================
# Question types and field values
# ===========================================================================

class TestQuestionTypes:
    def test_radiogrid_values_saved(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        # radiogrid sub-questions are TEXT columns, values stored as strings
        assert result.g1_q1 == "3"
        assert result.g1_q2 == "5"

    def test_slider_value_saved(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "72", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.rating == 72

    def test_field_value_saved(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "Hello World", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.name == "Hello World"

    def test_num_field_value_saved(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "42",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.age == 42

    def test_missing_field_gets_default(self, bofs_app_with_questionnaires):
        """Omit 'name' field from form → default value (empty string)."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        # Deliberately omit 'name'
        submit_questionnaire_data(client, "survey", data_dict={
            "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.name == ""  # text field default

    def test_questionnaire_interactions_logged(self, bofs_app_with_questionnaires):
        """POST with questionnaireInteractions JSON → QuestionnaireInteraction rows."""
        app = bofs_app_with_questionnaires
        app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = True
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        events = (
            '{"questionID":"g1_q1","eventType":"change","timestamp":1704110400.123,"value":"3"};'
            '{"questionID":"g1_q2","eventType":"change","timestamp":1704110401.456,"value":"5"}'
        )

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
            "questionnaireInteractions": events,
        })

        rows = app.db.session.query(app.db.QuestionnaireInteraction).filter(
            app.db.QuestionnaireInteraction.participantID == pid,
            app.db.QuestionnaireInteraction.questionnaire == "survey",
        ).order_by(app.db.QuestionnaireInteraction.timestamp).all()

        assert len(rows) == 2
        assert rows[0].questionID == "g1_q1"
        assert rows[0].value == "3"
        assert rows[0].eventType == "change"
        assert rows[1].questionID == "g1_q2"
        assert rows[1].value == "5"
        assert rows[1].eventType == "change"


# ===========================================================================
# Computed properties
# ===========================================================================

class TestComputedProperties:
    def test_duration_property_works(self, bofs_app_with_questionnaires):
        """record.duration() = (timeEnded - timeStarted).total_seconds()"""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        duration = result.duration()
        assert isinstance(duration, float)
        assert duration >= 0

    def test_calculated_fields_computed(self, bofs_app_with_questionnaires):
        """participant_calculations 'grid_total' = g1_q1 + g1_q2"""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
        })

        result = app.questionnaires["survey"].fetch_all_data()[0]
        assert result.grid_total() == 8.0


# ===========================================================================
# Question-level show_if — branching renders + tolerates hidden answers
# ===========================================================================

import os
import toml

SHOW_IF_QUESTIONNAIRE = {
    "title": "Branched",
    "instructions": "Answer about yourself.",
    "questions": [
        {"questiontype": "num_field", "id": "age",
         "instructions": "Enter age"},
        {"questiontype": "field", "id": "guardian_name",
         "instructions": "Guardian name (only if under 18)",
         "show_if": "age < 18"},
    ],
}


@pytest.fixture
def bofs_app_with_show_if(tmp_path):
    """A BOFS app whose survey has a show_if-gated question."""
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "branched.json").write_text(
        json.dumps(SHOW_IF_QUESTIONNAIRE), encoding="utf-8"
    )
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Branched", "path": "questionnaire/branched"},
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


class TestShowIfRendering:
    def test_data_show_if_is_emitted(self, bofs_app_with_show_if):
        app = bofs_app_with_show_if
        client = app.test_client()
        create_participant_via_consent(client, app)

        resp = client.get("/questionnaire/branched")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # The conditional question should carry the AST and the marker class.
        assert "bofs-conditional" in html
        assert "data-show-if=" in html
        # The script tags must be loaded so the engine actually runs.
        assert "bofs_expressions.js" in html
        assert "questionnaire_branching.js" in html

    def test_unconditional_question_has_no_show_if_attribute(
        self, bofs_app_with_show_if
    ):
        app = bofs_app_with_show_if
        client = app.test_client()
        create_participant_via_consent(client, app)

        html = client.get("/questionnaire/branched").data.decode("utf-8")
        # The age question wrapper should NOT carry data-show-if (only the
        # guardian_name wrapper does). Find a window around the `name="age"`
        # input and verify it has no data-show-if in that block.
        import re
        # Look for ".question padding" wrappers; each ends at `</div>` of inputs.
        wrappers = re.findall(
            r'<div class="question padding[^"]*"(?:[^>]*)>.*?<input[^>]*name="age"',
            html, re.DOTALL
        )
        assert wrappers, "Age question wrapper not found in HTML"
        assert "data-show-if" not in wrappers[0]

    def test_submit_without_hidden_field_uses_default(
        self, bofs_app_with_show_if
    ):
        """When a participant is over 18, guardian_name is hidden client-side
        and the form submits no value for it. The server falls back to the
        column default — the submission must succeed."""
        app = bofs_app_with_show_if
        client = app.test_client()
        create_participant_via_consent(client, app)

        resp = submit_questionnaire_data(client, "branched", data_dict={
            "age": "30",
            # guardian_name intentionally omitted (would be hidden in browser).
        })
        assert resp.status_code == 200

        result = app.questionnaires["branched"].fetch_all_data()[0]
        assert result.age == 30
        # Default for a string field is the empty string per JSONQuestionnaireColumn.
        assert result.guardian_name == ""
