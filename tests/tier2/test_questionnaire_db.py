"""Tier 2 tests for JSONQuestionnaire database methods.

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture from conftest.py.
"""

import json
from datetime import datetime

import pytest

from BOFS.services.participant_questionnaire import ParticipantQuestionnaireService
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

DATATYPE_QUESTIONNAIRE = {
    "title": "Datatype Test",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "float_val", "datatype": "float"},
        {"questiontype": "field", "id": "dt_val", "datatype": "datetime"},
        {"questiontype": "field", "id": "bool_val", "datatype": "boolean"},
    ],
}


GROUP_QUESTIONNAIRE = {
    "title": "Grouped",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "intro"},
        {
            "questiontype": "group",
            "id": "demographics",
            "text": "About you",
            "show_sub_labels": True,
            "questions": [
                {"questiontype": "field", "id": "first_name"},
                {"questiontype": "num_field", "id": "age"},
                {"questiontype": "slider", "id": "experience"},
            ],
        },
        {"questiontype": "field", "id": "outro"},
    ],
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

    def test_radiogrid_parent_id_is_not_a_column(self, bofs_app):
        """The radiogrid's own id is structural; only its rows are stored."""
        q = write_questionnaire_file(bofs_app, "grid_q2", RADIOGRID_QUESTIONNAIRE)
        table_cols = {c.name for c in q.db_class.__table__.c}
        assert "grid" not in table_cols

    def test_group_sub_columns_created(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "grouped", GROUP_QUESTIONNAIRE)
        table_cols = {c.name for c in q.db_class.__table__.c}
        for name in ("intro", "first_name", "age", "experience", "outro"):
            assert name in table_cols, f"missing column {name}"

    def test_group_parent_id_is_not_a_column(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "grouped2", GROUP_QUESTIONNAIRE)
        table_cols = {c.name for c in q.db_class.__table__.c}
        assert "demographics" not in table_cols

    def test_group_sub_column_types(self, bofs_app):
        """Each sub-question's column type derives from its own questiontype,
        not from the group."""
        q = write_questionnaire_file(bofs_app, "grouped3", GROUP_QUESTIONNAIRE)
        cols = q.db_class.__table__.c
        assert cols["first_name"].type.__class__.__name__ in ("Text", "TEXT")
        assert cols["age"].type.__class__.__name__ == "Integer"
        assert cols["experience"].type.__class__.__name__ == "Integer"

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

    def test_calculated_field_with_missing_radiogrid_value(self, bofs_app):
        # Reported bug: a participant submits a radiogrid with no option
        # selected, so the sub-question column stores "" (string default).
        # The calculation must yield None (missing), not raise TypeError —
        # otherwise an unrelated participant breaks the entire export.
        radio_calc = {
            "title": "Grid Calc",
            "instructions": "",
            "questions": [
                {
                    "questiontype": "radiogrid",
                    "id": "grid",
                    "labels": ["1", "2", "3", "4", "5"],
                    "q_text": [
                        {"id": "q1", "text": "Item one"},
                        {"id": "q2", "text": "Item two"},
                        {"id": "q3", "text": "Item three"},
                    ],
                }
            ],
            "participant_calculations": {
                "ExampleQualityMean": "mean([q1, 6-q2, q3])",
                "ExampleQualitySum": "q1 + 6-q2 + q3",
            },
        }
        q = write_questionnaire_file(bofs_app, "grid_calc", radio_calc)
        instance = q.db_class()
        # q1 and q3 answered; q2 left blank — radiogrid columns default to "".
        instance.q1 = "4"
        instance.q2 = ""
        instance.q3 = "5"

        assert instance.ExampleQualityMean() is None
        assert instance.ExampleQualitySum() is None

        # Same calc with all values present should produce a real result.
        instance.q2 = "2"
        assert instance.ExampleQualitySum() == 13.0

    def test_calculated_field_error_message_includes_field_state(self, bofs_app):
        # Genuine type errors (e.g. a non-numeric string in arithmetic) still
        # raise — but the error must name the referenced fields and their
        # values so the researcher can diagnose without guessing.
        bad_calc = {
            "title": "Bad",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "name"},
            ],
            "participant_calculations": {
                "doubled": "name * 2 - 1",
            },
        }
        q = write_questionnaire_file(bofs_app, "bad_calc", bad_calc)
        instance = q.db_class()
        instance.name = "alice"  # non-numeric, non-empty string

        with pytest.raises(Exception) as exc_info:
            instance.doubled()
        msg = str(exc_info.value)
        assert "doubled" in msg
        assert "Referenced fields" in msg
        assert "name=" in msg

    def test_no_calculations_ok(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)
        assert q.get_calculated_fields() == []

    def test_radiogrid_columns_are_nullable(self, bofs_app):
        # Required so the optional N/A column can record NULL. Unconditional
        # so column generation doesn't depend on per-grid options.
        q = write_questionnaire_file(bofs_app, "grid_null", RADIOGRID_QUESTIONNAIRE)
        for row_id in ("g_q1", "g_q2"):
            col = q.db_class.__table__.c[row_id]
            assert col.nullable is True, (
                f"radiogrid row column {row_id!r} should be nullable"
            )

    def test_store_labels_calc_reference_rejected_at_load(self, bofs_app):
        # store_labels grids hold non-numeric strings, so referencing them
        # from a calculated field is a configuration error — surface it at
        # load time rather than producing a calc that always errors.
        bad = {
            "title": "Label calc",
            "instructions": "",
            "questions": [
                {
                    "questiontype": "radiogrid",
                    "id": "grid",
                    "store_labels": True,
                    "labels": ["Low", "High"],
                    "q_text": [
                        {"id": "row_1", "text": "Item one"},
                        {"id": "row_2", "text": "Item two"},
                    ],
                }
            ],
            "participant_calculations": {
                "total": "row_1 + row_2",
            },
        }
        with pytest.raises(Exception, match="store_labels"):
            write_questionnaire_file(bofs_app, "label_calc", bad)


# ===========================================================================
# TestRadiogridSubmission — N/A column and store_labels behaviour
# ===========================================================================

class TestRadiogridSubmission:
    @staticmethod
    def _create_participant(app):
        p = app.db.Participant()
        p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        p.ipAddress = "127.0.0.1"
        p.userAgent = "test"
        p.condition = 1
        p.finished = False
        app.db.session.add(p)
        app.db.session.commit()
        return p.participantID

    def test_na_submission_stores_null(self, bofs_app):
        na_grid = {
            "title": "N/A grid",
            "instructions": "",
            "questions": [
                {
                    "questiontype": "radiogrid",
                    "id": "grid",
                    "na_column": True,
                    "labels": ["1", "2", "3"],
                    "q_text": [
                        {"id": "row_1", "text": "Item one"},
                        {"id": "row_2", "text": "Item two"},
                    ],
                }
            ],
        }
        q = write_questionnaire_file(bofs_app, "na_grid", na_grid)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/na_grid",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "row_1": "2",
                "row_2": "",  # N/A — empty value from the N/A radio
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        results = q.fetch_all_data()
        assert len(results) == 1
        assert results[0].row_1 == "2"
        assert results[0].row_2 is None

    def test_na_submission_calc_returns_none(self, bofs_app):
        # A calc that references an N/A row should short-circuit to None
        # rather than crashing the export.
        na_calc = {
            "title": "N/A calc",
            "instructions": "",
            "questions": [
                {
                    "questiontype": "radiogrid",
                    "id": "grid",
                    "na_column": True,
                    "labels": ["1", "2", "3"],
                    "q_text": [
                        {"id": "row_1", "text": "Item one"},
                        {"id": "row_2", "text": "Item two"},
                    ],
                }
            ],
            "participant_calculations": {
                "total": "row_1 + row_2",
            },
        }
        q = write_questionnaire_file(bofs_app, "na_calc", na_calc)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/na_calc",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "row_1": "2",
                "row_2": "",
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        results = q.fetch_all_data()
        assert results[0].total() is None

    def test_store_labels_submission_records_label_string(self, bofs_app):
        label_grid = {
            "title": "Label grid",
            "instructions": "",
            "questions": [
                {
                    "questiontype": "radiogrid",
                    "id": "grid",
                    "store_labels": True,
                    "labels": ["Strongly disagree", "Neutral", "Strongly agree"],
                    "q_text": [
                        {"id": "row_1", "text": "Item one"},
                    ],
                }
            ],
        }
        q = write_questionnaire_file(bofs_app, "label_grid", label_grid)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/label_grid",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "row_1": "Strongly agree",
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        results = q.fetch_all_data()
        assert results[0].row_1 == "Strongly agree"


# ===========================================================================
# TestShowIfCompilation — show_if predicates parse at create_db_class time
# ===========================================================================

SHOW_IF_QUESTIONNAIRE = {
    "title": "Branched",
    "instructions": "",
    "questions": [
        {"questiontype": "num_field", "id": "age"},
        {"questiontype": "field", "id": "guardian_name",
         "show_if": "age < 18"},
    ],
}


class TestShowIfCompilation:
    def test_show_if_ast_attached(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "branched", SHOW_IF_QUESTIONNAIRE)
        guardian = q.json_data["questions"][1]
        assert "_show_if_ast" in guardian
        # Sanity-check the AST shape: comparison of `age` against 18.
        ast = guardian["_show_if_ast"]
        assert ast["op"] == "<"
        assert ast["args"][0] == {"var": "age"}
        assert ast["args"][1] == {"const": 18}

    def test_show_if_unparseable_fails_at_load(self, bofs_app, tmp_path):
        bad = {
            "title": "Bad",
            "instructions": "",
            "questions": [
                {"questiontype": "num_field", "id": "age"},
                {"questiontype": "field", "id": "x", "show_if": "age <"},
            ],
        }
        with pytest.raises(Exception, match="show_if"):
            write_questionnaire_file(bofs_app, "bad_show_if", bad)

    def test_show_if_disallowed_construct_fails_at_load(self, bofs_app):
        bad = {
            "title": "Bad",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "x",
                 "show_if": "__import__('os')"},
            ],
        }
        with pytest.raises(Exception, match="show_if"):
            write_questionnaire_file(bofs_app, "evil_show_if", bad)


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

    def test_float_column_type(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "dt_types", DATATYPE_QUESTIONNAIRE)
        col = q.db_class.__table__.c["float_val"]
        assert col.type.__class__.__name__ == "Float"

    def test_datetime_column_type(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "dt_types", DATATYPE_QUESTIONNAIRE)
        col = q.db_class.__table__.c["dt_val"]
        assert col.type.__class__.__name__ == "DateTime"

    def test_boolean_column_type(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "dt_types", DATATYPE_QUESTIONNAIRE)
        col = q.db_class.__table__.c["bool_val"]
        assert col.type.__class__.__name__ == "Boolean"


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
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid

            ParticipantQuestionnaireService(pid).handle_submission(q)

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
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        # Second submission (update)
        with bofs_app.test_request_context(
            "/questionnaire/survey",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:05:00",
                "name": "Bob",
                "rating": "5",
                "age": "25",
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

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
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

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
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q, tag="pre")

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
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        results = q.fetch_all_data()
        assert results[0].name == ""  # default for text fields

    def test_questionnaire_interactions_logged(self, bofs_app):
        bofs_app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = True
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        events = (
            '{"questionID":"g_q1","eventType":"focus","timestamp":1704110400.000,"value":""}\n'
            '{"questionID":"g_q1","eventType":"change","timestamp":1704110400.500,"value":"2"}\n'
            '{"questionID":"g_q1","eventType":"blur","timestamp":1704110401.000,"value":"2"}\n'
            '{"questionID":"g_q2","eventType":"change","timestamp":1704110402.000,"value":"3"}'
        )

        with bofs_app.test_request_context(
            "/questionnaire/grid_q",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "g_q1": "2",
                "g_q2": "3",
                "questionnaireInteractions": events,
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        rows = bofs_app.db.session.query(
            bofs_app.db.QuestionnaireInteraction
        ).filter(
            bofs_app.db.QuestionnaireInteraction.participantID == pid,
            bofs_app.db.QuestionnaireInteraction.questionnaire == "grid_q",
        ).order_by(bofs_app.db.QuestionnaireInteraction.timestamp).all()

        assert len(rows) == 4
        assert [r.eventType for r in rows] == ["focus", "change", "blur", "change"]
        assert [r.questionID for r in rows] == ["g_q1", "g_q1", "g_q1", "g_q2"]
        assert [r.value for r in rows] == ["", "2", "2", "3"]
        assert rows[0].timestamp == datetime.fromtimestamp(1704110400.000)

    def test_interaction_event_malformed_does_not_lose_others(self, bofs_app):
        bofs_app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = True
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        # Middle event is broken JSON; the surrounding events should still persist.
        events = (
            '{"questionID":"g_q1","eventType":"change","timestamp":1704110400.000,"value":"2"}\n'
            '{this is not valid json}\n'
            '{"questionID":"g_q2","eventType":"change","timestamp":1704110402.000,"value":"3"}'
        )

        with bofs_app.test_request_context(
            "/questionnaire/grid_q",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "g_q1": "2",
                "g_q2": "3",
                "questionnaireInteractions": events,
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        rows = bofs_app.db.session.query(
            bofs_app.db.QuestionnaireInteraction
        ).filter(
            bofs_app.db.QuestionnaireInteraction.participantID == pid,
        ).order_by(bofs_app.db.QuestionnaireInteraction.timestamp).all()

        assert len(rows) == 2
        assert [r.questionID for r in rows] == ["g_q1", "g_q2"]

    def test_interaction_value_with_delimiter_chars(self, bofs_app):
        # Regression: a free-text value containing semicolons (the old
        # delimiter) and apostrophes must survive intact. The client
        # serializes each event with JSON.stringify and joins with newlines,
        # which escapes any literal newline, so the value is delimiter-safe.
        bofs_app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = True
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        free_text = (
            "I liked him a lot for his personality and attitude; "
            "he was pretty much what I expected; I didn't mind."
        )
        events = "\n".join([
            json.dumps({"questionID": "g_q1", "eventType": "blur",
                        "timestamp": 1704110400.000, "value": free_text}),
            json.dumps({"questionID": "g_q2", "eventType": "change",
                        "timestamp": 1704110401.000, "value": "3"}),
        ])

        with bofs_app.test_request_context(
            "/questionnaire/grid_q",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "g_q1": "2",
                "g_q2": "3",
                "questionnaireInteractions": events,
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        rows = bofs_app.db.session.query(
            bofs_app.db.QuestionnaireInteraction
        ).filter(
            bofs_app.db.QuestionnaireInteraction.participantID == pid,
        ).order_by(bofs_app.db.QuestionnaireInteraction.timestamp).all()

        assert len(rows) == 2
        assert rows[0].value == free_text
        assert rows[1].value == "3"

    def test_interaction_logging_disabled(self, bofs_app):
        # Default config has LOG_QUESTIONNAIRE_INTERACTIONS = False
        bofs_app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = False
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        events = (
            '{"questionID":"g_q1","eventType":"change","timestamp":1704110400.000,"value":"2"}'
        )

        with bofs_app.test_request_context(
            "/questionnaire/grid_q",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "g_q1": "2",
                "g_q2": "3",
                "questionnaireInteractions": events,
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        count = bofs_app.db.session.query(
            bofs_app.db.QuestionnaireInteraction
        ).count()
        assert count == 0

    def test_text_stats_event_persisted(self, bofs_app):
        bofs_app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = True
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        stats = "keystrokes=12,backspaces=2,pastes=0,pasted_chars=0,length=14,duration_ms=8000,first_key_ms=600"
        events = (
            '{"questionID":"essay","eventType":"text_stats","timestamp":1704110400.000,"value":"'
            + stats + '"}'
        )

        with bofs_app.test_request_context(
            "/questionnaire/grid_q",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "g_q1": "2",
                "g_q2": "3",
                "questionnaireInteractions": events,
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        row = bofs_app.db.session.query(
            bofs_app.db.QuestionnaireInteraction
        ).filter_by(eventType="text_stats").one()
        assert row.questionID == "essay"
        assert row.value == stats

    def test_paste_event_persisted(self, bofs_app):
        bofs_app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] = True
        q = write_questionnaire_file(bofs_app, "grid_q", RADIOGRID_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        events = (
            '{"questionID":"essay","eventType":"paste","timestamp":1704110400.000,"value":"chars=42"}'
        )

        with bofs_app.test_request_context(
            "/questionnaire/grid_q",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "g_q1": "2",
                "g_q2": "3",
                "questionnaireInteractions": events,
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        row = bofs_app.db.session.query(
            bofs_app.db.QuestionnaireInteraction
        ).filter_by(eventType="paste").one()
        assert row.questionID == "essay"
        assert row.value == "chars=42"

    def test_group_submission_persists_each_sub(self, bofs_app):
        """End-to-end submission: each sub-question's form value lands in
        its own column under the flat sub-id namespace."""
        q = write_questionnaire_file(bofs_app, "grouped_e2e", GROUP_QUESTIONNAIRE)
        pid = self._create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/questionnaire/grouped_e2e",
            method="POST",
            data={
                "timeStarted": "2024-01-01 12:00:00",
                "intro": "Hi",
                "first_name": "Alice",
                "age": "30",
                "experience": "7",
                "outro": "Bye",
                "questionnaireInteractions": "",
            },
        ):
            from flask import session
            session["participantID"] = pid
            ParticipantQuestionnaireService(pid).handle_submission(q)

        results = q.fetch_all_data()
        assert len(results) == 1
        row = results[0]
        assert row.intro == "Hi"
        assert row.first_name == "Alice"
        assert row.age == 30
        assert row.experience == 7
        assert row.outro == "Bye"


# ===========================================================================
# Group prior-value injection — exercises the recursive branch in
# _inject_prior_values that lets sub-questions go through their own
# type-specific expansion (so a sub-audio gets prior_started, etc.).
# ===========================================================================

class TestGroupPriorValues:
    def test_group_sub_field_repopulates_value(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "grouped_pv", GROUP_QUESTIONNAIRE)
        questionnaire_q = q.json_data["questions"][1]  # the group
        injected = ParticipantQuestionnaireService._inject_prior_values(
            questionnaire_q, {"first_name": "Alice", "age": 30, "experience": 7}
        )
        subs = injected["questions"]
        by_id = {s["id"]: s for s in subs}
        assert by_id["first_name"]["value"] == "Alice"
        assert by_id["first_name"]["has_value"] is True
        assert by_id["age"]["value"] == 30
        assert by_id["age"]["has_value"] is True
        assert by_id["experience"]["value"] == 7

    def test_group_sub_audio_prior_keys_surface(self, bofs_app):
        """Audio sub-questions must get prior_started / prior_ended /
        prior_listened keys so the audio template can repopulate hidden
        fields when a participant returns mid-flow."""
        data = {
            "title": "Group with audio",
            "instructions": "",
            "questions": [
                {
                    "questiontype": "group",
                    "id": "g",
                    "questions": [
                        {"questiontype": "audio", "id": "clip", "src": "/a.ogg"},
                    ],
                }
            ],
        }
        q = write_questionnaire_file(bofs_app, "grouped_audio_pv", data)
        group_q = q.json_data["questions"][0]
        prior = {
            "clip_started": 1.5,
            "clip_ended": 12.0,
            "clip_listened": 10.5,
        }
        injected = ParticipantQuestionnaireService._inject_prior_values(
            group_q, prior
        )
        sub = injected["questions"][0]
        assert sub["prior_started"] == 1.5
        assert sub["prior_ended"] == 12.0
        assert sub["prior_listened"] == 10.5


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

    def _create_participant(self, app, finished=False, condition=1):
        """Create a participant with the given attributes."""
        p = app.db.Participant()
        p.mTurkID = ""
        p.ipAddress = ""
        p.userAgent = ""
        p.condition = condition
        p.finished = finished
        app.db.session.add(p)
        app.db.session.commit()
        return p

    def test_fetch_all_data(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SIMPLE_QUESTIONNAIRE)

        p1 = self._create_participant(bofs_app)
        p2 = self._create_participant(bofs_app)

        self._seed_data(bofs_app, q, [
            {"participantID": p1.participantID, "name": "Alice", "rating": 4, "age": 30},
            {"participantID": p2.participantID, "name": "Bob", "rating": 5, "age": 25},
        ])

        results = q.fetch_all_data()
        assert len(results) == 2

    def test_fetch_finished_data(self, bofs_app):
        """fetch_finished_data should only return data for finished participants.

        Currently FAILS: the method filters on Participant.finished without
        joining on participantID, producing a cartesian product that returns
        all rows when *any* participant is finished.
        """
        q = write_questionnaire_file(bofs_app, "survey2", SIMPLE_QUESTIONNAIRE)

        p_done = self._create_participant(bofs_app, finished=True)
        p_not = self._create_participant(bofs_app, finished=False)

        self._seed_data(bofs_app, q, [
            {"participantID": p_done.participantID, "name": "Done", "rating": 5, "age": 30},
            {"participantID": p_not.participantID, "name": "NotDone", "rating": 3, "age": 20},
        ])

        results = q.fetch_finished_data()
        assert len(results) == 1
        assert results[0].name == "Done"

    def test_fetch_column_data_by_condition(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey3", SIMPLE_QUESTIONNAIRE)

        p_c1 = self._create_participant(bofs_app, condition=1)
        p_c2 = self._create_participant(bofs_app, condition=2)

        self._seed_data(bofs_app, q, [
            {"participantID": p_c1.participantID, "name": "C1", "rating": 4, "age": 30},
            {"participantID": p_c2.participantID, "name": "C2", "rating": 5, "age": 25},
        ])

        results = q.fetch_column_data("rating", condition=1)
        assert len(results) == 1
        assert results[0][0] == 4  # fetch_column_data returns tuples

    def test_fetch_column_data_condition_zero(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey4", SIMPLE_QUESTIONNAIRE)

        p_c0 = self._create_participant(bofs_app, condition=0)
        p_c1 = self._create_participant(bofs_app, condition=1)

        self._seed_data(bofs_app, q, [
            {"participantID": p_c0.participantID, "name": "C0", "rating": 2, "age": 20},
            {"participantID": p_c1.participantID, "name": "C1", "rating": 8, "age": 40},
        ])

        results = q.fetch_column_data("rating", condition=0)
        assert len(results) == 1
        assert results[0][0] == 2


# ===========================================================================
# TestQuestionnaireInteractionNoCollision
# ===========================================================================

class TestQuestionnaireInteractionNoCollision:
    """A questionnaire named 'interaction' must load successfully now that the
    system table uses the 'bofs_' prefix."""

    def write_interaction_q(self, app, data):
        import json, os
        q_dir = os.path.join(app.root_path, "questionnaires")
        os.makedirs(q_dir, exist_ok=True)
        filepath = os.path.join(q_dir, "interaction.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_interaction_questionnaire_loads(self, bofs_app):
        """Previously 'interaction' silently failed because it collided with
        'questionnaire_interaction'. After the rename, it should load."""
        self.write_interaction_q(bofs_app, {
            "title": "Interaction Test",
            "instructions": "",
            "questions": [
                {"questiontype": "field", "id": "answer"},
            ]
        })
        from BOFS.startup import load_questionnaire
        q_dir = bofs_app.root_path + "/questionnaires"
        q = load_questionnaire(bofs_app, q_dir, "interaction")
        assert q is not None
        assert q.file_name == "interaction"
        assert q.db_class.__tablename__ == "questionnaire_interaction"


# ===========================================================================
# TestQuestionnaireCollisionLoudGuard
# ===========================================================================

class TestQuestionnaireCollisionLoudGuard:
    """A questionnaire whose table name collides with an existing metadata
    entry should produce an error diagnostic, not a silent skip."""

    def test_collision_emits_error_diagnostic(self, bofs_app):
        from BOFS.setup_diagnostics import DiagnosticCollector
        bofs_app.setup_diagnostics = DiagnosticCollector()
        bofs_app.setup_diagnostics.bind(bofs_app)

        # Add a raw table to metadata whose name will collide with
        # the questionnaire table name "questionnaire_collide_target".
        from sqlalchemy import Table, Column, Integer
        t = Table("questionnaire_collide_target", bofs_app.db.metadata,
                   Column("id", Integer, primary_key=True))

        from BOFS.startup import load_questionnaire
        import json, os
        q_dir = os.path.join(bofs_app.root_path, "questionnaires")
        os.makedirs(q_dir, exist_ok=True)
        filepath = os.path.join(q_dir, "collide_target.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "title": "Collision",
                "instructions": "",
                "questions": [{"questiontype": "field", "id": "x"}],
            }, f)

        q = load_questionnaire(bofs_app, q_dir, "collide_target")
        assert q is None

        errors = bofs_app.setup_diagnostics.by_severity("error")
        assert any(
            "collide_target" in e.message and "collides" in e.message
            for e in errors
        )

        bofs_app.db.metadata.remove(t)
