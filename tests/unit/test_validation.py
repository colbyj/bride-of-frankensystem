"""Tests for the BOFS questionnaire validation module."""

import pytest

from BOFS.validation import (
    ValidationResult,
    is_sql_safe,
    validate_structure,
    validate_question_types,
    validate_question_ids,
    validate_field_ids,
    validate_calculations,
    validate_questionnaire,
    validate_page_list_references,
    BUILTIN_QUESTION_TYPES,
    RESERVED_COLUMNS,
)


# ===========================================================================
# is_sql_safe
# ===========================================================================

class TestIsSqlSafe:
    def test_simple_name(self):
        assert is_sql_safe("age")

    def test_underscore_prefix(self):
        assert is_sql_safe("_private")

    def test_mixed_case_with_digits(self):
        assert is_sql_safe("Item2_score")

    def test_starts_with_digit(self):
        assert not is_sql_safe("123field")

    def test_contains_dash(self):
        assert not is_sql_safe("field-name")

    def test_contains_space(self):
        assert not is_sql_safe("field name")

    def test_contains_dot(self):
        assert not is_sql_safe("field.name")

    def test_empty_string(self):
        assert not is_sql_safe("")


# ===========================================================================
# validate_structure
# ===========================================================================

class TestValidateStructure:
    def test_valid_structure(self, sample_questionnaire_json):
        errors = validate_structure(sample_questionnaire_json, "test")
        assert len(errors) == 0

    def test_missing_questions_key(self):
        data = {"title": "Bad", "instructions": "No questions here"}
        errors = validate_structure(data, "bad")
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "questions" in errors[0].message

    def test_questions_not_a_list(self):
        data = {"questions": "not a list"}
        errors = validate_structure(data, "bad")
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "list" in errors[0].message

    def test_empty_questions_is_warning(self):
        data = {"questions": []}
        errors = validate_structure(data, "empty")
        assert len(errors) == 1
        assert errors[0].severity == "warning"


# ===========================================================================
# validate_question_types
# ===========================================================================

class TestValidateQuestionTypes:
    def test_all_builtin_types_valid(self, sample_questionnaire_json):
        errors = validate_question_types(sample_questionnaire_json, "test")
        assert len(errors) == 0

    def test_unknown_type(self):
        data = {"questions": [{"questiontype": "magical_widget", "id": "x"}]}
        errors = validate_question_types(data, "bad")
        assert len(errors) == 1
        assert "magical_widget" in errors[0].message
        assert errors[0].severity == "error"

    def test_close_match_suggestion(self):
        data = {"questions": [{"questiontype": "dropdown", "id": "x"}]}
        errors = validate_question_types(data, "bad")
        assert len(errors) == 1
        assert "drop_down" in errors[0].suggestion

    def test_missing_questiontype(self):
        data = {"questions": [{"id": "orphan"}]}
        errors = validate_question_types(data, "bad")
        assert len(errors) == 1
        assert "missing" in errors[0].message.lower()

    def test_question_not_a_dict(self):
        data = {"questions": ["not a dict"]}
        errors = validate_question_types(data, "bad")
        assert len(errors) == 1
        assert "not a JSON object" in errors[0].message

    def test_custom_valid_types(self):
        custom_types = frozenset({"custom_widget"})
        data = {"questions": [{"questiontype": "custom_widget", "id": "x"}]}
        errors = validate_question_types(data, "test", valid_types=custom_types)
        assert len(errors) == 0


# ===========================================================================
# validate_question_ids
# ===========================================================================

class TestValidateQuestionIds:
    def test_textview_no_id_ok(self):
        data = {"questions": [{"questiontype": "textview", "title": "Info"}]}
        errors = validate_question_ids(data, "test")
        assert len(errors) == 0

    def test_field_without_id_warns(self):
        data = {"questions": [{"questiontype": "field"}]}
        errors = validate_question_ids(data, "test")
        assert len(errors) == 1
        assert errors[0].severity == "warning"

    def test_nested_item_without_id_warns(self):
        data = {"questions": [{
            "questiontype": "radiogrid",
            "id": "grid",
            "q_text": [
                {"id": "q1", "text": "Item 1"},
                {"text": "Item 2 - no id"},
            ]
        }]}
        errors = validate_question_ids(data, "test")
        assert len(errors) == 1
        assert "sub-item" in errors[0].message


# ===========================================================================
# validate_field_ids
# ===========================================================================

class TestValidateFieldIds:
    def test_valid_ids(self, sample_questionnaire_json):
        errors = validate_field_ids(sample_questionnaire_json, "test")
        assert len(errors) == 0

    def test_duplicate_ids(self):
        data = {"questions": [
            {"questiontype": "field", "id": "duplicate"},
            {"questiontype": "field", "id": "duplicate"},
        ]}
        errors = validate_field_ids(data, "bad")
        assert any("uplicate" in e.message for e in errors)

    def test_sql_unsafe_starts_with_digit(self):
        data = {"questions": [{"questiontype": "field", "id": "123bad"}]}
        errors = validate_field_ids(data, "bad")
        assert any("not a valid column name" in e.message for e in errors)

    def test_sql_unsafe_has_dash(self):
        data = {"questions": [{"questiontype": "field", "id": "has-dash"}]}
        errors = validate_field_ids(data, "bad")
        assert any("not a valid column name" in e.message for e in errors)

    def test_sql_unsafe_has_space(self):
        data = {"questions": [{"questiontype": "field", "id": "has space"}]}
        errors = validate_field_ids(data, "bad")
        assert any("not a valid column name" in e.message for e in errors)

    def test_reserved_column_name(self):
        data = {"questions": [{"questiontype": "field", "id": "participantID"}]}
        errors = validate_field_ids(data, "bad")
        assert any("reserved" in e.message.lower() for e in errors)

    def test_all_reserved_names_caught(self):
        for name in RESERVED_COLUMNS:
            data = {"questions": [{"questiontype": "field", "id": name}]}
            errors = validate_field_ids(data, "bad")
            assert any("reserved" in e.message.lower() for e in errors), \
                f"Reserved name '{name}' was not caught"


# ===========================================================================
# validate_calculations
# ===========================================================================

class TestValidateCalculations:
    def test_no_calculations_is_fine(self):
        data = {"questions": [{"questiontype": "slider", "id": "q1"}]}
        errors = validate_calculations(data, "test")
        assert len(errors) == 0

    def test_valid_calculation(self):
        data = {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "slider", "id": "q2"},
            ],
            "participant_calculations": {
                "total": "q1 + q2"
            }
        }
        errors = validate_calculations(data, "test")
        assert len(errors) == 0

    def test_unknown_field_reference(self):
        data = {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": {
                "total": "q1 + nonexistent"
            }
        }
        errors = validate_calculations(data, "bad")
        assert len(errors) == 1
        assert "nonexistent" in errors[0].message
        assert errors[0].severity == "warning"

    def test_sql_unsafe_calc_name(self):
        data = {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": {
                "123bad": "q1"
            }
        }
        errors = validate_calculations(data, "bad")
        assert any("not a valid identifier" in e.message for e in errors)

    def test_reserved_calc_name(self):
        data = {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": {
                "participantID": "q1"
            }
        }
        errors = validate_calculations(data, "bad")
        assert any("reserved" in e.message.lower() for e in errors)

    def test_calculations_not_dict(self):
        data = {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": "not a dict"
        }
        errors = validate_calculations(data, "bad")
        assert len(errors) == 1
        assert errors[0].severity == "error"

    def test_builtin_functions_not_flagged(self):
        """mean, sum, etc. should not be treated as unknown field references."""
        data = {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "slider", "id": "q2"},
            ],
            "participant_calculations": {
                "avg": "mean([q1, q2])"
            }
        }
        errors = validate_calculations(data, "test")
        assert len(errors) == 0

    def test_with_sample_fixture(self, sample_questionnaire_with_calculations):
        """The sample fixture with calculations should pass validation."""
        errors = validate_calculations(sample_questionnaire_with_calculations, "test")
        # There may be warnings about preprocessed field refs, but no errors
        fatal = [e for e in errors if e.severity == "error"]
        assert len(fatal) == 0


# ===========================================================================
# validate_questionnaire (full pipeline)
# ===========================================================================

class TestValidateQuestionnaire:
    def test_valid_questionnaire_no_errors(self, sample_questionnaire_json):
        errors = validate_questionnaire(sample_questionnaire_json, "test")
        fatal = [e for e in errors if e.severity == "error"]
        assert len(fatal) == 0

    def test_valid_questionnaire_with_calculations(self, sample_questionnaire_with_calculations):
        errors = validate_questionnaire(sample_questionnaire_with_calculations, "test")
        fatal = [e for e in errors if e.severity == "error"]
        assert len(fatal) == 0

    def test_multiple_errors_collected(self):
        """A questionnaire with several problems should collect all errors."""
        data = {"questions": [
            {"questiontype": "invalid_type", "id": "123bad"},
            {"questiontype": "field", "id": "participantID"},
        ]}
        errors = validate_questionnaire(data, "multi_error")
        fatal = [e for e in errors if e.severity == "error"]
        # Should catch: invalid type, unsafe id "123bad", reserved name "participantID"
        assert len(fatal) >= 3

    def test_missing_questions_stops_early(self):
        """If structure check fails, don't run further checks."""
        data = {"title": "No questions"}
        errors = validate_questionnaire(data, "bad")
        assert len(errors) == 1  # Only the structure error

    def test_empty_dict(self):
        errors = validate_questionnaire({}, "empty")
        assert len(errors) >= 1
        assert errors[0].severity == "error"


# ===========================================================================
# validate_page_list_references
# ===========================================================================

class TestValidatePageListReferences:
    def test_all_refs_exist(self, simple_page_list_data):
        paths = {"/path/to/questionnaires": ["example", "example_grid"]}
        errors = validate_page_list_references(simple_page_list_data, paths)
        assert len(errors) == 0

    def test_missing_ref(self, simple_page_list_data):
        # Only provide one of the two questionnaires
        paths = {"/path/to/questionnaires": ["example"]}
        errors = validate_page_list_references(simple_page_list_data, paths)
        assert len(errors) == 1
        assert "example_grid" in errors[0].message

    def test_conditional_routing_refs(self, conditional_page_list_data):
        # Provide all referenced questionnaires
        paths = {"/q": ["pre", "control_q", "control_followup", "treatment_q", "post"]}
        errors = validate_page_list_references(conditional_page_list_data, paths)
        assert len(errors) == 0

    def test_conditional_routing_missing_ref(self, conditional_page_list_data):
        # Miss one from inside conditional routing
        paths = {"/q": ["pre", "control_q", "treatment_q", "post"]}
        errors = validate_page_list_references(conditional_page_list_data, paths)
        assert len(errors) == 1
        assert "control_followup" in errors[0].message

    def test_no_questionnaire_refs(self):
        page_list = [
            {"name": "Consent", "path": "consent"},
            {"name": "End", "path": "end"},
        ]
        errors = validate_page_list_references(page_list, {})
        assert len(errors) == 0


# ===========================================================================
# ValidationResult
# ===========================================================================

class TestValidationResult:
    def test_str_format_error(self):
        r = ValidationResult("error", "survey.json", "Something broke", "Fix it")
        s = str(r)
        assert "ERROR" in s
        assert "survey.json" in s
        assert "Something broke" in s
        assert "Fix it" in s

    def test_str_format_warning(self):
        r = ValidationResult("warning", "survey.json", "Minor issue")
        s = str(r)
        assert "WARNING" in s

    def test_repr(self):
        r = ValidationResult("error", "test", "msg")
        assert "ValidationResult" in repr(r)
