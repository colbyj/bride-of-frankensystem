"""Tests for JSONQuestionnaireColumn and pure methods of JSONQuestionnaire."""

import json
import pytest

from BOFS.JSONQuestionnaire import JSONQuestionnaireColumn, JSONQuestionnaire


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_questionnaire(tmp_path, name, data):
    """Write a questionnaire dict as <name>.json and return a JSONQuestionnaire."""
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return JSONQuestionnaire(str(tmp_path), name, True)


# ===========================================================================
# JSONQuestionnaireColumn — question_type resolution
# ===========================================================================

class TestColumnQuestionTypeResolution:
    """Test the constructor's handling of the question_type parameter."""

    def test_question_type_none_reads_from_definition(self):
        defn = {"id": "x", "questiontype": "slider"}
        col = JSONQuestionnaireColumn(defn, question_type=None)
        assert col.data_type == "integer"
        assert col.default == 0

    def test_question_type_none_no_definition_key_defaults_to_string(self):
        defn = {"id": "x"}
        col = JSONQuestionnaireColumn(defn, question_type=None)
        assert col.data_type == "string"
        assert col.default == ""

    def test_explicit_question_type_respected(self):
        """When question_type is explicitly passed, it should be used."""
        defn = {"id": "x"}
        col = JSONQuestionnaireColumn(defn, question_type="slider")
        assert col.data_type == "integer"
        assert col.default == 0

    def test_explicit_question_type_overrides_definition(self):
        """When both question_type arg and definition key exist, the explicit arg should win."""
        defn = {"id": "x", "questiontype": "num_field"}
        col = JSONQuestionnaireColumn(defn, question_type="slider")
        assert col.data_type == "integer"
        assert col.default == 0

    def test_question_type_default_none(self):
        defn = {"id": "x", "questiontype": "checklist"}
        col = JSONQuestionnaireColumn(defn)
        assert col.data_type == "integer"
        assert col.default == 0


# ===========================================================================
# JSONQuestionnaireColumn — data type mapping via definition
# ===========================================================================

def test_slider_sets_integer_via_definition():
    col = JSONQuestionnaireColumn({"id": "s1", "questiontype": "slider"})
    assert col.data_type == "integer"
    assert col.default == 0


def test_num_field_sets_integer_via_definition():
    col = JSONQuestionnaireColumn({"id": "n1", "questiontype": "num_field"})
    assert col.data_type == "integer"
    assert col.default == 0


def test_checklist_sets_integer_via_definition():
    col = JSONQuestionnaireColumn({"id": "c1", "questiontype": "checklist"})
    assert col.data_type == "integer"
    assert col.default == 0


def test_radiolist_stays_string():
    col = JSONQuestionnaireColumn({"id": "r1", "questiontype": "radiolist"})
    assert col.data_type == "string"
    assert col.default == ""


def test_field_stays_string():
    col = JSONQuestionnaireColumn({"id": "f1", "questiontype": "field"})
    assert col.data_type == "string"
    assert col.default == ""


def test_unknown_type_stays_string():
    col = JSONQuestionnaireColumn({"id": "u1", "questiontype": "fancy_widget"})
    assert col.data_type == "string"
    assert col.default == ""


def test_slider_case_insensitive():
    col = JSONQuestionnaireColumn({"id": "s", "questiontype": "Slider"})
    assert col.data_type == "integer"


# ===========================================================================
# JSONQuestionnaireColumn — picture_select data type auto-detection
# ===========================================================================

def test_picture_select_string_values_stay_string():
    defn = {
        "id": "fav", "questiontype": "picture_select",
        "images": [{"src": "/a.png", "value": "a"}, {"src": "/b.png", "value": "b"}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "string"
    assert col.default == ""


def test_picture_select_integer_values_become_integer():
    defn = {
        "id": "fav", "questiontype": "picture_select",
        "images": [{"src": "/a.png", "value": 1}, {"src": "/b.png", "value": 2}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "integer"
    assert col.default == 0


def test_picture_select_float_values_become_float():
    defn = {
        "id": "fav", "questiontype": "picture_select",
        "images": [{"src": "/a.png", "value": 0.5}, {"src": "/b.png", "value": 1.5}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "float"
    assert col.default == 0


def test_picture_select_mixed_int_float_becomes_float():
    defn = {
        "id": "fav", "questiontype": "picture_select",
        "images": [{"src": "/a.png", "value": 1}, {"src": "/b.png", "value": 1.5}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "float"


def test_picture_select_mixed_int_string_stays_string():
    defn = {
        "id": "fav", "questiontype": "picture_select",
        "images": [{"src": "/a.png", "value": 1}, {"src": "/b.png", "value": "two"}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "string"


def test_picture_select_bool_values_stay_string():
    """bool is a subclass of int in Python — make sure we don't pick it up as integer."""
    defn = {
        "id": "fav", "questiontype": "picture_select",
        "images": [{"src": "/a.png", "value": True}, {"src": "/b.png", "value": False}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "string"


def test_picture_select_no_images_stays_string():
    defn = {"id": "fav", "questiontype": "picture_select"}
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "string"


def test_picture_select_explicit_datatype_overrides_autodetect():
    defn = {
        "id": "fav", "questiontype": "picture_select", "datatype": "string",
        "images": [{"src": "/a.png", "value": 1}, {"src": "/b.png", "value": 2}],
    }
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "string"


# ===========================================================================
# JSONQuestionnaireColumn — explicit datatype override
# ===========================================================================

def test_datatype_override_to_float():
    defn = {"id": "x", "questiontype": "slider", "datatype": "float"}
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "float"
    assert col.default == 0


def test_datatype_override_to_string_from_integer():
    defn = {"id": "x", "questiontype": "slider", "datatype": "string"}
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "string"
    assert col.default == ""


def test_datatype_override_datetime():
    defn = {"id": "x", "datatype": "datetime"}
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "datetime"
    assert col.default == ""


def test_datatype_override_boolean():
    defn = {"id": "x", "datatype": "boolean"}
    col = JSONQuestionnaireColumn(defn)
    assert col.data_type == "boolean"
    assert col.default == ""


# ===========================================================================
# JSONQuestionnaireColumn — id and get_type_ddl
# ===========================================================================

def test_id_is_set():
    col = JSONQuestionnaireColumn({"id": "my_column"})
    assert col.id == "my_column"


def test_missing_id_raises_key_error():
    with pytest.raises(KeyError):
        JSONQuestionnaireColumn({})


@pytest.mark.parametrize("data_type, expected_ddl", [
    ("integer", "INTEGER"),
    ("float", "NUMERIC"),
    ("datetime", "DATETIME"),
    ("boolean", "BOOLEAN"),
    ("string", "TEXT"),
    ("anything_else", "TEXT"),
])
def test_get_type_ddl(data_type, expected_ddl):
    defn = {"id": "x", "datatype": data_type}
    col = JSONQuestionnaireColumn(defn)
    assert col.get_type_ddl() == expected_ddl


def test_get_type_ddl_default_string():
    col = JSONQuestionnaireColumn({"id": "x", "questiontype": "field"})
    assert col.get_type_ddl() == "TEXT"


def test_get_type_ddl_integer_from_slider():
    col = JSONQuestionnaireColumn({"id": "x", "questiontype": "slider"})
    assert col.get_type_ddl() == "INTEGER"


# ===========================================================================
# JSONQuestionnaire — constructor
# ===========================================================================

def test_constructor_loads_json(tmp_path):
    data = {"title": "Test", "questions": []}
    q = _write_questionnaire(tmp_path, "test_q", data)
    assert q.file_name == "test_q"
    assert q.is_in_db is True
    assert q.json_data == data
    assert q.db_class is None


def test_constructor_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        JSONQuestionnaire(str(tmp_path), "nonexistent", False)


# ===========================================================================
# JSONQuestionnaire — fetch_fields
# ===========================================================================

def test_fetch_fields_returns_all_fields(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "slider",
                "q_text": [
                    {"id": "mood_happy", "text": "Happy"},
                    {"id": "mood_sad", "text": "Sad"},
                ],
            },
            {"questiontype": "field", "id": "comments"},
            {
                "questiontype": "num_field",
                "questions": [{"id": "age", "text": "Age"}],
            },
            {
                "questiontype": "checklist",
                "questions": [{"id": "agree_tos", "text": "Agree"}],
            },
        ],
    }
    q = _write_questionnaire(tmp_path, "ff", data)
    fields = q.fetch_fields()
    field_ids = [f.id for f in fields]
    assert field_ids == ["mood_happy", "mood_sad", "comments", "age", "agree_tos"]


def test_fetch_fields_standalone_with_questiontype(tmp_path):
    """Standalone questions (with 'id' at top level) read questiontype from
    their own definition, which works correctly."""
    data = {
        "questions": [
            {"questiontype": "slider", "id": "standalone_slider"},
        ],
    }
    q = _write_questionnaire(tmp_path, "ff3", data)
    fields = q.fetch_fields()
    assert fields[0].data_type == "integer"


def test_fetch_fields_video_expands_into_three_columns(tmp_path):
    """A video question with an id expands into _started, _ended, _watched columns,
    all of float datatype. No bare {id} column is created."""
    data = {
        "questions": [
            {"questiontype": "video", "id": "tutorial", "src": "https://example.com/v.webm"},
        ],
    }
    q = _write_questionnaire(tmp_path, "vid_expand", data)
    fields = q.fetch_fields()
    field_ids = [f.id for f in fields]
    assert field_ids == ["tutorial_started", "tutorial_ended", "tutorial_watched"]
    assert all(f.data_type == "float" for f in fields)


def test_fetch_fields_video_without_id_emits_no_columns(tmp_path):
    """A video question without an id is purely display — no DB columns."""
    data = {
        "questions": [
            {"questiontype": "video", "src": "https://example.com/v.webm"},
        ],
    }
    q = _write_questionnaire(tmp_path, "vid_noid", data)
    assert q.fetch_fields() == []


def test_fetch_fields_audio_expands_into_three_columns(tmp_path):
    """An audio question with an id expands into _started, _ended, _listened columns,
    all of float datatype."""
    data = {
        "questions": [
            {"questiontype": "audio", "id": "clip", "src": "https://example.com/a.ogg"},
        ],
    }
    q = _write_questionnaire(tmp_path, "aud_expand", data)
    fields = q.fetch_fields()
    field_ids = [f.id for f in fields]
    assert field_ids == ["clip_started", "clip_ended", "clip_listened"]
    assert all(f.data_type == "float" for f in fields)


def test_fetch_fields_image_click_single_expands_to_xy_floats(tmp_path):
    """Default (single-click) image_click stores natural-pixel x,y as two FLOAT
    columns named {id}_x and {id}_y. No bare {id} column is created."""
    data = {
        "questions": [
            {"questiontype": "image_click", "id": "spot",
             "image_src": "/static/m.png"},
        ],
    }
    q = _write_questionnaire(tmp_path, "ic_single", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["spot_x", "spot_y"]
    assert all(f.data_type == "float" for f in fields)


def test_fetch_fields_image_click_explicit_max_clicks_one_same_as_default(tmp_path):
    data = {
        "questions": [
            {"questiontype": "image_click", "id": "spot",
             "image_src": "/static/m.png", "max_clicks": 1},
        ],
    }
    q = _write_questionnaire(tmp_path, "ic_single_explicit", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["spot_x", "spot_y"]
    assert all(f.data_type == "float" for f in fields)


def test_fetch_fields_image_click_multi_uses_single_text_column(tmp_path):
    """max_clicks > 1 stores the click array as JSON in one TEXT column at {id}."""
    data = {
        "questions": [
            {"questiontype": "image_click", "id": "spots",
             "image_src": "/static/m.png", "max_clicks": 3},
        ],
    }
    q = _write_questionnaire(tmp_path, "ic_multi", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["spots"]
    assert fields[0].data_type == "string"


def test_fetch_fields_image_click_unlimited_uses_single_text_column(tmp_path):
    """max_clicks == 0 (unlimited) also routes to the single TEXT column shape."""
    data = {
        "questions": [
            {"questiontype": "image_click", "id": "spots",
             "image_src": "/static/m.png", "max_clicks": 0},
        ],
    }
    q = _write_questionnaire(tmp_path, "ic_unlimited", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["spots"]
    assert fields[0].data_type == "string"


def test_fetch_fields_empty_questions(tmp_path):
    data = {"questions": []}
    q = _write_questionnaire(tmp_path, "empty", data)
    assert q.fetch_fields() == []


def test_fetch_fields_no_questions_key(tmp_path):
    data = {"title": "NoQ"}
    q = _write_questionnaire(tmp_path, "noq", data)
    assert q.fetch_fields() == []


def test_fetch_fields_q_text_fallback(tmp_path):
    """When a question group uses 'q_text' instead of 'questions', fetch_fields
    renames it to 'questions' and processes normally."""
    data = {
        "questions": [
            {
                "questiontype": "slider",
                "q_text": [
                    {"id": "item_a", "text": "A"},
                    {"id": "item_b", "text": "B"},
                ],
            },
        ],
    }
    q = _write_questionnaire(tmp_path, "qtext", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["item_a", "item_b"]


def test_fetch_fields_resets_on_second_call(tmp_path):
    data = {"questions": [{"questiontype": "field", "id": "x"}]}
    q = _write_questionnaire(tmp_path, "reset", data)
    fields1 = q.fetch_fields()
    fields2 = q.fetch_fields()
    assert len(fields1) == len(fields2)


def test_fetch_fields_nested_question_without_id_skipped(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "slider",
                "questions": [
                    {"id": "has_id", "text": "OK"},
                    {"text": "No id here"},
                ],
            },
        ],
    }
    q = _write_questionnaire(tmp_path, "noid", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["has_id"]


# ===========================================================================
# JSONQuestionnaire — get_field
# ===========================================================================

def test_get_field_found(tmp_path):
    data = {"questions": [{"questiontype": "field", "id": "x"}]}
    q = _write_questionnaire(tmp_path, "gf", data)
    q.fetch_fields()
    assert q.get_field("x").id == "x"


def test_get_field_not_found(tmp_path):
    data = {"questions": [{"questiontype": "field", "id": "x"}]}
    q = _write_questionnaire(tmp_path, "gf2", data)
    q.fetch_fields()
    assert q.get_field("nonexistent") is None


def test_get_field_before_fetch_fields(tmp_path):
    data = {"questions": [{"questiontype": "field", "id": "x"}]}
    q = _write_questionnaire(tmp_path, "gf3", data)
    assert q.get_field("x") is None


# ===========================================================================
# JSONQuestionnaire — calculation parsing via the expression engine
#
# These cover the same surface as the old `preprocess_calculation_string`
# tests did: that field IDs are recognized, that partial matches are not,
# that non-Python-identifier IDs (e.g. ``01_inv``) still resolve, and that
# absent fields fall through to a parser-level error.
# ===========================================================================

from BOFS.expressions import (
    ExpressionError,
    parse_with_field_ids,
    referenced_fields,
)


def test_calc_parser_recognizes_field_ids(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "radiogrid",
                "questions": [
                    {"id": "q1", "text": "Q1"},
                    {"id": "q2", "text": "Q2"},
                    {"id": "q3", "text": "Q3"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "calc", data)
    q.fetch_fields()
    field_ids = [f.id for f in q.fetch_fields()]
    ast = parse_with_field_ids("[q1, q2, q3]", field_ids)
    assert referenced_fields(ast) == {"q1", "q2", "q3"}


def test_calc_parser_arithmetic(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "radiogrid",
                "questions": [
                    {"id": "q1", "text": "Q1"},
                    {"id": "q2", "text": "Q2"},
                    {"id": "q3", "text": "Q3"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "calc2", data)
    q.fetch_fields()
    field_ids = [f.id for f in q.fetch_fields()]
    ast = parse_with_field_ids("q1 + q2 - q3", field_ids)
    assert referenced_fields(ast) == {"q1", "q2", "q3"}


def test_calc_parser_lone_field_id(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "radiogrid",
                "questions": [{"id": "q1", "text": "Q1"}],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "calc3", data)
    field_ids = [f.id for f in q.fetch_fields()]
    ast = parse_with_field_ids("q1", field_ids)
    assert ast == {"var": "q1"}


def test_calc_parser_unknown_identifier_is_caller_problem(tmp_path):
    # When no field IDs are declared, an identifier in the expression is
    # still parsed as a `var` reference; the evaluator (not the parser) is
    # responsible for raising on unknown variables.
    data = {"questions": []}
    q = _write_questionnaire(tmp_path, "calc_empty", data)
    q.fetch_fields()
    ast = parse_with_field_ids("x + y + z", [])
    assert referenced_fields(ast) == {"x", "y", "z"}


def test_calc_parser_does_not_match_partial(tmp_path):
    # ``q1`` is a known field, ``q1x`` is not — substitution must not match
    # the prefix of an unrelated word, otherwise we'd parse-rewrite
    # ``q1x`` into ``_bofs_pid_0x``.
    data = {
        "questions": [
            {
                "questiontype": "radiogrid",
                "questions": [{"id": "q1x", "text": "Q1x"}],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "partial", data)
    q.fetch_fields()
    field_ids = [f.id for f in q.fetch_fields()]
    ast = parse_with_field_ids("q1x", field_ids)
    assert ast == {"var": "q1x"}


def test_calc_parser_handles_non_python_identifier_ids(tmp_path):
    # Real deployed projects use IDs like ``01_inv`` that aren't valid Python
    # identifiers. The substitution wrapper must still produce an AST that
    # references the original field name.
    data = {
        "questions": [
            {
                "questiontype": "radiogrid",
                "questions": [
                    {"id": "01_inv", "text": "Inverted item 1"},
                    {"id": "02", "text": "Item 2"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "non_py", data)
    q.fetch_fields()
    field_ids = [f.id for f in q.fetch_fields()]
    ast = parse_with_field_ids("(5 - 01_inv) + 02", field_ids)
    assert referenced_fields(ast) == {"01_inv", "02"}


def test_calc_parser_rejects_disallowed_construct(tmp_path):
    data = {"questions": [{"questiontype": "field", "id": "x"}]}
    q = _write_questionnaire(tmp_path, "bad", data)
    q.fetch_fields()
    with pytest.raises(ExpressionError):
        parse_with_field_ids("__import__('os')", ["x"])
