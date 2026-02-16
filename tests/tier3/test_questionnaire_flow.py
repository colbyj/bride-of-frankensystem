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

    def test_grid_item_clicks_logged(self, bofs_app_with_questionnaires):
        """POST with gridItemClicks JSON → RadioGridLog records."""
        app = bofs_app_with_questionnaires
        client = app.test_client()
        pid = create_participant_via_consent(client, app)

        click_data = (
            '{"id":"g1_q1","value":"3","time":"1704110400.123"};'
            '{"id":"g1_q2","value":"5","time":"1704110401.456"}'
        )

        submit_questionnaire_data(client, "survey", data_dict={
            "name": "A", "rating": "4", "age": "30",
            "g1_q1": "3", "g1_q2": "5",
            "gridItemClicks": click_data,
        })

        logs = app.db.session.query(app.db.RadioGridLog).filter(
            app.db.RadioGridLog.participantID == pid,
            app.db.RadioGridLog.questionnaire == "survey",
        ).order_by(app.db.RadioGridLog.timeClicked).all()

        assert len(logs) == 2
        assert logs[0].questionID == "g1_q1"
        assert logs[0].value == "3"
        assert logs[1].questionID == "g1_q2"
        assert logs[1].value == "5"


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
