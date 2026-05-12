"""Tests for the BOFS questionnaire validation module."""

import pytest

from BOFS.validation import (
    ValidationResult,
    is_sql_safe,
    is_sql_expression_safe,
    is_python_attribute_safe,
    validate_structure,
    validate_question_types,
    validate_question_ids,
    validate_field_ids,
    validate_picture_select,
    validate_image_click,
    validate_calculations,
    validate_questionnaire,
    validate_page_list_references,
    validate_show_if,
    validate_table,
    BUILTIN_QUESTION_TYPES,
    RESERVED_COLUMNS,
    RESERVED_EXPRESSION_NAMES,
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
# Group container validation
# ===========================================================================

class TestValidateGroup:
    def test_valid_group_passes(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "demographics",
            "text": "About you",
            "questions": [
                {"questiontype": "field", "id": "first_name"},
                {"questiontype": "num_field", "id": "age"},
            ],
        }]}
        errors = validate_question_ids(data, "test")
        assert errors == []

    def test_group_empty_questions_is_error(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [],
        }]}
        errors = validate_question_ids(data, "test")
        assert any(e.severity == "error" and "no sub-questions" in e.message
                   for e in errors)

    def test_group_missing_questions_is_error(self):
        data = {"questions": [{"questiontype": "group", "id": "g"}]}
        errors = validate_question_ids(data, "test")
        assert any(e.severity == "error" and "no sub-questions" in e.message
                   for e in errors)

    def test_group_with_textview_sub_is_allowed(self):
        """Textview is allowed inside groups for mid-section prose. It has
        no id and produces no DB column, so no warnings either."""
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [
                {"questiontype": "field", "id": "first_name"},
                {"questiontype": "textview", "text": "Now your work history."},
                {"questiontype": "field", "id": "employer"},
            ],
        }]}
        errors = validate_question_ids(data, "test")
        assert errors == []

    def test_group_with_nested_group_sub_is_error(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "outer",
            "questions": [
                {"questiontype": "group", "id": "inner",
                 "questions": [{"questiontype": "field", "id": "x"}]},
            ],
        }]}
        errors = validate_question_ids(data, "test")
        assert any(e.severity == "error" and "Nested groups" in e.message
                   for e in errors)

    def test_group_sub_without_id_warns(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [
                {"questiontype": "field"},  # missing id
            ],
        }]}
        errors = validate_question_ids(data, "test")
        assert any(e.severity == "warning" and "sub-item" in e.message
                   for e in errors)

    def test_group_sub_radiogrid_row_without_id_warns(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [
                {"questiontype": "radiogrid", "id": "r",
                 "q_text": [
                     {"id": "ok", "text": "OK"},
                     {"text": "no id"},
                 ]},
            ],
        }]}
        errors = validate_question_ids(data, "test")
        assert any(e.severity == "warning" and "row" in e.message
                   for e in errors)

    def test_group_sub_with_unknown_type_is_error(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [
                {"questiontype": "magical_widget", "id": "x"},
            ],
        }]}
        errors = validate_question_types(data, "test")
        assert any(e.severity == "error" and "magical_widget" in e.message
                   for e in errors)

    def test_group_sub_with_close_match_suggests(self):
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [
                {"questiontype": "dropdown", "id": "x"},
            ],
        }]}
        errors = validate_question_types(data, "test")
        assert any("drop_down" in (e.suggestion or "") for e in errors)

    def test_group_field_id_uniqueness_across_subs(self):
        """Sub-IDs share the flat field-id namespace; duplicates inside one
        group must be detected."""
        data = {"questions": [{
            "questiontype": "group",
            "id": "g",
            "questions": [
                {"questiontype": "field", "id": "dup"},
                {"questiontype": "num_field", "id": "dup"},
            ],
        }]}
        errors = validate_field_ids(data, "test")
        assert any("uplicate" in e.message for e in errors)

    def test_group_field_id_uniqueness_across_top_level_and_group(self):
        data = {"questions": [
            {"questiontype": "field", "id": "shared"},
            {
                "questiontype": "group",
                "id": "g",
                "questions": [
                    {"questiontype": "num_field", "id": "shared"},
                ],
            },
        ]}
        errors = validate_field_ids(data, "test")
        assert any("uplicate" in e.message for e in errors)

    def test_group_parent_id_does_not_register_as_field(self):
        """The group's own id is structural — it must not collide with a
        sub-question's id of the same name (since the group id is not a
        field at all)."""
        data = {"questions": [{
            "questiontype": "group",
            "id": "shared",
            "questions": [
                {"questiontype": "field", "id": "shared"},
            ],
        }]}
        errors = validate_field_ids(data, "test")
        # No duplicate-id error: 'shared' appears once (only the sub).
        assert not any("uplicate" in e.message for e in errors)

    def test_group_audio_sub_expands_in_field_ids(self):
        """An audio sub-question inside a group registers its expanded ids
        (e.g. clip_started) for uniqueness checks."""
        data = {"questions": [
            {"questiontype": "field", "id": "clip_started"},
            {
                "questiontype": "group",
                "id": "g",
                "questions": [
                    {"questiontype": "audio", "id": "clip", "src": "/a.ogg"},
                ],
            },
        ]}
        errors = validate_field_ids(data, "test")
        assert any("uplicate" in e.message and "clip_started" in e.message
                   for e in errors)


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

    def test_reserved_expression_name_condition(self):
        data = {"questions": [{"questiontype": "field", "id": "condition"}]}
        errors = validate_field_ids(data, "bad")
        assert any(e.severity == "error" and "condition" in e.message
                   and "reserved" in e.message.lower()
                   for e in errors)

    def test_all_reserved_expression_names_caught(self):
        for name in RESERVED_EXPRESSION_NAMES:
            data = {"questions": [{"questiontype": "field", "id": name}]}
            errors = validate_field_ids(data, "bad")
            assert any(e.severity == "error" and "reserved" in e.message.lower()
                       for e in errors), \
                f"Reserved expression name '{name}' was not caught"

    def test_python_keyword_field_id_rejected(self):
        for kw in ("class", "for", "if", "return", "lambda"):
            data = {"questions": [{"questiontype": "field", "id": kw}]}
            errors = validate_field_ids(data, "bad")
            assert any(e.severity == "error" and "keyword" in e.message.lower()
                       for e in errors), \
                f"Python keyword '{kw}' was not caught as a field ID"


class TestIsPythonAttributeSafe:
    def test_valid_identifier(self):
        assert is_python_attribute_safe("age")
        assert is_python_attribute_safe("_private")
        assert is_python_attribute_safe("q1_score")

    def test_python_keyword_rejected(self):
        assert not is_python_attribute_safe("class")
        assert not is_python_attribute_safe("if")

    def test_starts_with_digit_rejected(self):
        assert not is_python_attribute_safe("1bad")


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

    def test_reserved_expression_calc_name_condition(self):
        data = {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": {
                "condition": "q1"
            }
        }
        errors = validate_calculations(data, "bad")
        assert any(e.severity == "error" and "condition" in e.message
                   and "reserved" in e.message.lower()
                   for e in errors)

    def test_python_keyword_calc_name_rejected(self):
        data = {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": {
                "class": "q1"
            }
        }
        errors = validate_calculations(data, "bad")
        assert any(e.severity == "error" and "keyword" in e.message.lower()
                   for e in errors)


class TestValidateTable:
    def test_valid_table(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": [
                {"fields": {"total": "sum(score)"}}
            ],
        }
        errors = validate_table(data, "trials")
        assert errors == []

    def test_column_collides_with_export_field(self):
        data = {
            "columns": {"total": {"type": "integer"}},
            "exports": [
                {"fields": {"total": "sum(total)"}}
            ],
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "collides" in e.message
            for e in errors
        )

    def test_python_keyword_column(self):
        data = {
            "columns": {"class": {"type": "integer"}},
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "keyword" in e.message.lower()
            for e in errors
        )

    def test_python_keyword_export_field(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": [
                {"fields": {"return": "sum(score)"}}
            ],
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "keyword" in e.message.lower()
            for e in errors
        )

    def test_unsafe_column_name(self):
        data = {
            "columns": {"123bad": {"type": "integer"}},
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "valid identifier" in e.message
            for e in errors
        )

    def test_unsafe_export_field_name(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": [
                {"fields": {"123bad": "sum(score)"}}
            ],
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "valid identifier" in e.message
            for e in errors
        )

    def test_no_exports_block_is_fine(self):
        data = {"columns": {"score": {"type": "integer"}}}
        errors = validate_table(data, "trials")
        assert errors == []

    def test_columns_must_be_dict(self):
        data = {"columns": []}
        errors = validate_table(data, "trials")
        assert any(e.severity == "error" for e in errors)

    def test_exports_must_be_list(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": {"fields": {"total": "sum(score)"}},
        }
        errors = validate_table(data, "trials")
        assert any(e.severity == "error" for e in errors)

    def test_rejects_field_expression_with_semicolon(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": [
                {"fields": {"total": "0; DROP TABLE participant; --"}}
            ],
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "invalid SQL expression" in e.message
            for e in errors
        )

    def test_rejects_filter_with_union(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": [
                {
                    "filter": "1=1 UNION SELECT password FROM app_meta",
                    "fields": {"total": "sum(score)"},
                }
            ],
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "'filter' clause" in e.message
            for e in errors
        )

    def test_rejects_having_with_pragma(self):
        data = {
            "columns": {"score": {"type": "integer"}},
            "exports": [
                {
                    "group_by": "score",
                    "having": "pragma synchronous",
                    "fields": {"total": "sum(score)"},
                }
            ],
        }
        errors = validate_table(data, "trials")
        assert any(
            e.severity == "error" and "'having' clause" in e.message
            for e in errors
        )

    def test_real_world_expressions_accepted(self):
        data = {
            "columns": {
                "trial_index": {"type": "integer"},
                "correct": {"type": "boolean"},
                "rt": {"type": "float"},
                "phase": {"type": "string"},
            },
            "exports": [
                {
                    "filter": "phase = 'learning'",
                    "fields": {
                        "accuracy": "avg(case when correct then 1.0 else 0.0 end)",
                        "n_trials": "count(trial_index)",
                        "mean_rt": "avg(rt)",
                    },
                }
            ],
        }
        errors = validate_table(data, "trials")
        fatal = [e for e in errors if e.severity == "error"]
        assert fatal == []


# ===========================================================================
# is_sql_expression_safe
# ===========================================================================

class TestIsSqlExpressionSafe:
    @pytest.mark.parametrize("expr", [
        "score",
        "count(trial_index)",
        "count(*)",
        "avg(correct)",
        "sum(score)",
        "max(score)",
        "min(score)",
        "avg(case when correct then 1.0 else 0.0 end)",
        "avg(case when correct = 1 then 1.0 else 0.0 end)",
        "phase = 'learning'",
        "COUNT(trial_index)",  # case-insensitive
        "avg(rt) + 1.5",
        "coalesce(score, 0)",
        "round(avg(rt), 2)",
    ])
    def test_accepts_real_expressions(self, expr):
        ok, why = is_sql_expression_safe(expr)
        assert ok, f"rejected {expr!r}: {why}"

    @pytest.mark.parametrize("expr", [
        "0; DROP TABLE participant",
        "1=1) UNION SELECT password FROM app_meta",
        "count(*) /* x */",
        "select * from app_meta",
        "load_extension('evil.so')",
        'phase = "learning"',
        "phase = `learning`",
        "score -- comment",
        r"sum(score)\x00",
        "attach database x as y",
        "pragma synchronous",
        "phase = 'a' OR phase = 'b'; SELECT 1",
        "exec('rm -rf /')",
        # Unknown function rejected
        "random_func(score)",
        # Empty / non-string
        "",
        "   ",
    ])
    def test_rejects_attacks(self, expr):
        ok, _ = is_sql_expression_safe(expr)
        assert not ok, f"accepted dangerous expression: {expr!r}"

    def test_rejects_non_string(self):
        ok, _ = is_sql_expression_safe(123)
        assert not ok

    def test_rejects_overlong(self):
        ok, _ = is_sql_expression_safe("x" * 2000)
        assert not ok

    def test_escaped_quote_in_string_literal(self):
        # SQL standard double-quote escape inside a string is allowed.
        ok, _ = is_sql_expression_safe("phase = 'it''s fine'")
        assert ok

    def test_unterminated_string_rejected(self):
        ok, _ = is_sql_expression_safe("phase = 'oops")
        assert not ok

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
# validate_picture_select
# ===========================================================================

class TestValidatePictureSelect:
    def test_valid_picture_select(self):
        data = {"questions": [{
            "questiontype": "picture_select",
            "id": "fav",
            "images": [
                {"src": "/static/a.png", "value": "a", "label": "A"},
                {"src": "/static/b.png", "value": "b", "label": "B"},
            ]
        }]}
        errors = validate_picture_select(data, "test")
        assert len(errors) == 0

    def test_non_picture_select_questions_ignored(self, sample_questionnaire_json):
        errors = validate_picture_select(sample_questionnaire_json, "test")
        assert len(errors) == 0

    def test_missing_images_field(self):
        data = {"questions": [{"questiontype": "picture_select", "id": "fav"}]}
        errors = validate_picture_select(data, "bad")
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "images" in errors[0].message

    def test_images_not_a_list(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav",
            "images": "/static/foo.png"
        }]}
        errors = validate_picture_select(data, "bad")
        assert len(errors) == 1
        assert "must be a list" in errors[0].message

    def test_empty_images_list(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav", "images": []
        }]}
        errors = validate_picture_select(data, "bad")
        assert len(errors) == 1
        assert "empty" in errors[0].message

    def test_image_missing_src(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav",
            "images": [{"value": "a"}]
        }]}
        errors = validate_picture_select(data, "bad")
        assert any("src" in e.message for e in errors)

    def test_image_missing_value(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav",
            "images": [{"src": "/static/a.png"}]
        }]}
        errors = validate_picture_select(data, "bad")
        assert any("value" in e.message for e in errors)

    def test_image_not_an_object(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav",
            "images": ["/static/a.png"]
        }]}
        errors = validate_picture_select(data, "bad")
        assert any("not an object" in e.message for e in errors)

    def test_duplicate_values_warning(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav",
            "images": [
                {"src": "/static/a.png", "value": "x"},
                {"src": "/static/b.png", "value": "x"},
            ]
        }]}
        errors = validate_picture_select(data, "bad")
        warnings = [e for e in errors if e.severity == "warning"]
        assert any("reuses" in w.message for w in warnings)

    def test_integer_values_ok(self):
        data = {"questions": [{
            "questiontype": "picture_select", "id": "fav",
            "images": [
                {"src": "/static/a.png", "value": 1},
                {"src": "/static/b.png", "value": 2},
            ]
        }]}
        errors = validate_picture_select(data, "test")
        assert len(errors) == 0


# ===========================================================================
# validate_image_click
# ===========================================================================

class TestValidateImageClick:
    def test_valid_single_click(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png",
        }]}
        assert validate_image_click(data, "test") == []

    def test_valid_multi_click(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spots",
            "src": "/static/m.png", "max_clicks": 5,
        }]}
        assert validate_image_click(data, "test") == []

    def test_valid_unlimited_clicks(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spots",
            "src": "/static/m.png", "max_clicks": 0,
        }]}
        assert validate_image_click(data, "test") == []

    def test_non_image_click_questions_ignored(self, sample_questionnaire_json):
        assert validate_image_click(sample_questionnaire_json, "test") == []

    def test_missing_src(self):
        data = {"questions": [{"questiontype": "image_click", "id": "spot"}]}
        errors = validate_image_click(data, "bad")
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "'src'" in errors[0].message

    def test_empty_src(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot", "src": "",
        }]}
        errors = validate_image_click(data, "bad")
        assert any("'src'" in e.message for e in errors)

    def test_max_clicks_string_rejected(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "max_clicks": "lots",
        }]}
        errors = validate_image_click(data, "bad")
        assert any("max_clicks" in e.message for e in errors)

    def test_max_clicks_negative_rejected(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "max_clicks": -1,
        }]}
        errors = validate_image_click(data, "bad")
        assert any("max_clicks" in e.message for e in errors)

    def test_max_clicks_bool_rejected(self):
        # bool is an int subclass in Python — make sure we don't accidentally
        # accept True/False as a click count.
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "max_clicks": True,
        }]}
        errors = validate_image_click(data, "bad")
        assert any("max_clicks" in e.message for e in errors)

    def test_width_valid(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "width": 600,
        }]}
        assert validate_image_click(data, "test") == []

    def test_width_string_rejected(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "width": "600px",
        }]}
        errors = validate_image_click(data, "bad")
        assert any("width" in e.message for e in errors)

    def test_width_zero_rejected(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "width": 0,
        }]}
        errors = validate_image_click(data, "bad")
        assert any("width" in e.message for e in errors)

    def test_width_bool_rejected(self):
        data = {"questions": [{
            "questiontype": "image_click", "id": "spot",
            "src": "/static/m.png", "width": True,
        }]}
        errors = validate_image_click(data, "bad")
        assert any("width" in e.message for e in errors)


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


# ===========================================================================
# validate_show_if
# ===========================================================================

class TestValidateShowIf:
    def test_no_show_if_no_findings(self, sample_questionnaire_json):
        errors = validate_show_if(sample_questionnaire_json, "test")
        assert errors == []

    def test_valid_show_if(self):
        data = {
            "questions": [
                {"questiontype": "num_field", "id": "age"},
                {"questiontype": "field", "id": "guardian",
                 "show_if": "age < 18"},
            ]
        }
        errors = validate_show_if(data, "ok")
        assert errors == []

    def test_unparseable_show_if_is_error(self):
        data = {
            "questions": [
                {"questiontype": "num_field", "id": "age"},
                {"questiontype": "field", "id": "broken",
                 "show_if": "age <"},
            ]
        }
        errors = validate_show_if(data, "bad")
        assert any(e.severity == "error" and "show_if" in e.message
                   for e in errors)

    def test_disallowed_construct_is_error(self):
        data = {
            "questions": [
                {"questiontype": "field", "id": "x",
                 "show_if": "__import__('os')"},
            ]
        }
        errors = validate_show_if(data, "bad")
        assert any(e.severity == "error" for e in errors)

    def test_unknown_field_reference_is_warning(self):
        data = {
            "questions": [
                {"questiontype": "num_field", "id": "age"},
                {"questiontype": "field", "id": "guardian",
                 "show_if": "agee < 18"},  # typo
            ]
        }
        errors = validate_show_if(data, "typo")
        assert any(e.severity == "warning" and "agee" in e.message
                   for e in errors)

    def test_non_string_show_if_is_error(self):
        data = {
            "questions": [
                {"questiontype": "num_field", "id": "age"},
                {"questiontype": "field", "id": "g", "show_if": 42},
            ]
        }
        errors = validate_show_if(data, "bad")
        assert any(e.severity == "error" for e in errors)

    def test_show_if_with_non_python_identifier_field(self):
        # Field IDs that aren't valid Python identifiers (real BOFS pattern)
        # must still resolve through validate_show_if without crashing.
        data = {
            "questions": [
                {
                    "questiontype": "radiogrid",
                    "questions": [{"id": "01_inv", "text": "First"}],
                },
                {"questiontype": "field", "id": "follow",
                 "show_if": "01_inv > 3"},
            ]
        }
        errors = validate_show_if(data, "exotic")
        assert all(e.severity != "error" for e in errors), [
            (e.severity, e.message) for e in errors
        ]
