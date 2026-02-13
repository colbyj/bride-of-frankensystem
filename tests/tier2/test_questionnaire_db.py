"""Tier 2 tests for JSONQuestionnaire database methods.

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture from conftest.py.
"""

import json
from datetime import datetime

import pytest

from tests.conftest import write_questionnaire_file


# ===========================================================================
# Helpers
# ===========================================================================

SIMPLE_QUESTIONNAIRE = {
    "title": "Simple",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "name"},
        {"questiontype": "slider", "id": "rating"},
        {"questiontype": "num_field", "id": "age"},
    ],
}

RADIOGRID_QUESTIONNAIRE = {
    "title": "Grid",
    "instructions": "",
    "questions": [
        {
            "questiontype": "radiogrid",
            "id": "grid",
            "labels": ["1", "2", "3"],
            "q_text": [
                {"id": "g_q1", "text": "Item one"},
                {"id": "g_q2", "text": "Item two"},
            ],
        }
    ],
}

CALC_QUESTIONNAIRE = {
    "title": "Calculated",
    "instructions": "",
    "questions": [
        {"questiontype": "slider", "id": "q1"},
        {"questiontype": "slider", "id": "q2"},
    ],
    "participant_calculations": {
        "total": "q1 + q2",
        "average": "mean([q1, q2])",
    },
}


# ===========================================================================
# TestCreateDBClass
# ===========================================================================

class TestCreateDBClass:
    def test_table_name(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        assert q.db_class.__tablename__ == "questionnaire_survey"

    def test_primary_key_exists(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        pk_col = q.db_class.__table__.c["surveyID"]
        assert pk_col.primary_key
        assert pk_col.autoincrement

    def test_participant_foreign_key(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        fk_col = q.db_class.__table__.c["participantID"]
        fk_targets = [fk.target_fullname for fk in fk_col.foreign_keys]
        assert "participant.participantID" in fk_targets

    def test_standard_columns_exist(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        table_cols = {c.name for c in q.db_class.__table__.c}
        assert "tag" in table_cols
        assert "timeStarted" in table_cols
        assert "timeEnded" in table_cols

    def test_field_columns_created(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        table_cols = {c.name for c in q.db_class.__table__.c}
        assert "name" in table_cols
        assert "rating" in table_cols
        assert "age" in table_cols

    def test_radiogrid_nested_columns(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        table_cols = {c.name for c in q.db_class.__table__.c}
        assert "g_q1" in table_cols
        assert "g_q2" in table_cols

    def test_duration_property(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)

        instance = q.db_class()
        instance.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        instance.timeEnded = datetime(2024, 1, 1, 12, 1, 30)
        # duration is a lambda, not a property — call it
        assert instance.duration() == 90.0

    def test_db_class_is_set(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        assert q.db_class is not None
        assert hasattr(q.db_class, "__tablename__")

    def test_calculated_fields_registered(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "calc_q", CALC_QUESTIONNAIRE)
        calc_fields = q.get_calculated_fields()
        assert "total" in calc_fields
        assert "average" in calc_fields

    def test_calculated_field_evaluation(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "calc_q", CALC_QUESTIONNAIRE)

        instance = q.db_class()
        instance.q1 = 3
        instance.q2 = 7
        assert instance.total() == 10.0

    def test_no_calculations_ok(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        assert q.get_calculated_fields() == []


# ===========================================================================
# TestGenerateDBColumn
# ===========================================================================

class TestGenerateDBColumn:
    """Test that generate_db_column() produces correct SQLAlchemy column types."""

    def test_slider_is_integer(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "types", SIMPLE_QUESTIONNAIRE)
        col = q.db_class.__table__.c["rating"]
        assert isinstance(col.type, bofs_app.db.Integer.__class__) or \
               col.type.__class__.__name__ == "Integer"

    def test_num_field_is_integer(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "types", SIMPLE_QUESTIONNAIRE)
        col = q.db_class.__table__.c["age"]
        assert col.type.__class__.__name__ == "Integer"

    def test_field_is_text(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "types", SIMPLE_QUESTIONNAIRE)
        col = q.db_class.__table__.c["name"]
        assert col.type.__class__.__name__ in ("Text", "TEXT")

    def test_all_fields_not_nullable(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "types", SIMPLE_QUESTIONNAIRE)
        for field_name in ("name", "rating", "age"):
            col = q.db_class.__table__.c[field_name]
            assert col.nullable is False, f"Column '{field_name}' should not be nullable"


# ===========================================================================
# TestCreateBlank
# ===========================================================================

class TestCreateBlank:
    def test_returns_instance_of_db_class(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        blank = q.create_blank()
        assert isinstance(blank, q.db_class)

    def test_integer_fields_default_to_zero(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        blank = q.create_blank()
        assert blank.rating == 0
        assert blank.age == 0

    def test_string_fields_default_to_empty(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        blank = q.create_blank()
        assert blank.name == ""

    def test_tag_defaults_to_empty_string(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        blank = q.create_blank()
        assert blank.tag == ""


# ===========================================================================
# TestGetTableName
# ===========================================================================

class TestGetTableName:
    def test_returns_prefixed_name(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        assert q.get_table_name() == "questionnaire_survey"


# ===========================================================================
# TestHandleQuestionnaire
# ===========================================================================

class TestHandleQuestionnaire:
    """Test form submission handling. Requires Flask request context."""

    def _create_participant(self, app):
        """Insert a test participant and return its ID."""
        p = app.db.Participant()
        p.mTurkID = ""
        p.ipAddress = "127.0.0.1"
        p.userAgent = "test"
        p.condition = 1
        p.finished = False
        app.db.session.add(p)
        app.db.session.commit()
        return p.participantID

    def test_creates_new_record(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/survey",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "name": "Alice",
                "rating": "4",
                "age": "30",
                "gridItemClicks": "",
            },
        ):
            from flask import session
            session["participantID"] = pid

            q.handle_questionnaire()

        # Verify the record was created
        results = q.fetch_all_data()
        assert len(results) == 1
        assert results[0].name == "Alice"
        assert results[0].rating == 4  # SQLAlchemy coerces form string to Integer
        assert results[0].participantID == pid

    def test_updates_existing_record(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        # First submission
        with bofs_app.test_request_context(
            "/questionnaire/survey",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "name": "Alice",
                "rating": "4",
                "age": "30",
                "gridItemClicks": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            q.handle_questionnaire()

        # Second submission (update)
        with bofs_app.test_request_context(
            "/questionnaire/survey",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:05:00",
                "name": "Bob",
                "rating": "5",
                "age": "25",
                "gridItemClicks": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            q.handle_questionnaire()

        # Should have updated, not created a new record
        results = q.fetch_all_data()
        assert len(results) == 1
        assert results[0].name == "Bob"

    def test_sets_timestamps(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/survey",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "name": "Test",
                "rating": "1",
                "age": "20",
                "gridItemClicks": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            q.handle_questionnaire()

        results = q.fetch_all_data()
        assert results[0].timeStarted == datetime(2024, 1, 1, 12, 0, 0)
        assert results[0].timeEnded is not None

    def test_tagged_submission(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/survey/pre",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "name": "Tagged",
                "rating": "3",
                "age": "40",
                "gridItemClicks": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            q.handle_questionnaire(tag="pre")

        results = q.fetch_all_data()
        assert len(results) == 1
        assert results[0].tag == "pre"

    def test_missing_field_uses_default(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        # Don't include 'name' in form data
        with bofs_app.test_request_context(
            "/questionnaire/survey",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "rating": "4",
                "age": "30",
                "gridItemClicks": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            q.handle_questionnaire()

        results = q.fetch_all_data()
        assert results[0].name == ""  # default for text fields


# ===========================================================================
# TestFetchMethods
# ===========================================================================

class TestFetchMethods:
    def _seed_data(self, app, q, entries):
        """
        Seed the questionnaire table with test entries.
        Each entry is a dict with field values + participantID.
        """
        for entry in entries:
            obj = q.db_class()
            for k, v in entry.items():
                setattr(obj, k, v)
            obj.tag = ""
            obj.timeStarted = datetime(2024, 1, 1)
            obj.timeEnded = datetime(2024, 1, 1, 0, 1, 0)
            app.db.session.add(obj)
        app.db.session.commit()

    def test_fetch_all_data(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)

        # Create two participants
        p1 = bofs_app.db.Participant()
        p1.mTurkID = ""
        p1.ipAddress = ""
        p1.userAgent = ""
        p2 = bofs_app.db.Participant()
        p2.mTurkID = ""
        p2.ipAddress = ""
        p2.userAgent = ""
        bofs_app.db.session.add_all([p1, p2])
        bofs_app.db.session.commit()

        self._seed_data(bofs_app, q, [
            {"participantID": p1.participantID, "name": "Alice", "rating": 4, "age": 30},
            {"participantID": p2.participantID, "name": "Bob", "rating": 5, "age": 25},
        ])

        results = q.fetch_all_data()
        assert len(results) == 2
