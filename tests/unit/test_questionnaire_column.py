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
             "src": "/static/m.png"},
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
             "src": "/static/m.png", "max_clicks": 1},
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
             "src": "/static/m.png", "max_clicks": 3},
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
             "src": "/static/m.png", "max_clicks": 0},
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


def test_fetch_fields_radiogrid_parent_id_is_not_a_column(tmp_path):
    """Container questions (radiogrid, checklist) have structural parent IDs:
    the rows are stored, the parent itself is not. The parent id is only the
    HTML wrapper id."""
    data = {
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
    q = _write_questionnaire(tmp_path, "grid_no_parent_col", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["g_q1", "g_q2"]
    assert "grid" not in field_ids


def test_fetch_fields_checklist_parent_id_is_not_a_column(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "checklist",
                "id": "checks",
                "questions": [
                    {"id": "opt_a", "text": "Option A"},
                    {"id": "opt_b", "text": "Option B"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "check_no_parent_col", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["opt_a", "opt_b"]
    assert "checks" not in field_ids


# ===========================================================================
# JSONQuestionnaire — fetch_fields with `group` containers
# ===========================================================================

def test_fetch_fields_group_basic(tmp_path):
    """Group expands into one column per sub-question, in JSON order. Each
    sub-question's data_type is derived from its own questiontype (not the
    group's)."""
    data = {
        "questions": [
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
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_basic", data)
    fields = q.fetch_fields()
    field_ids = [f.id for f in fields]
    assert field_ids == ["first_name", "age", "experience"]
    by_id = {f.id: f.data_type for f in fields}
    assert by_id["first_name"] == "string"
    assert by_id["age"] == "integer"
    assert by_id["experience"] == "integer"


def test_fetch_fields_group_id_is_not_a_column(tmp_path):
    """The group's own id is structural (HTML wrapper) and never a column."""
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "bmi",
                "text": "Height and weight",
                "questions": [
                    {"questiontype": "num_field", "id": "height_cm"},
                    {"questiontype": "num_field", "id": "weight_kg"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_no_parent_col", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["height_cm", "weight_kg"]
    assert "bmi" not in field_ids


def test_fetch_fields_group_audio_sub_expands_into_three_columns(tmp_path):
    """Sub-questions go through the same expansion rules as top-level. An
    audio sub-question fans out into _started/_ended/_listened, all FLOAT."""
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "media_block",
                "questions": [
                    {"questiontype": "field", "id": "name"},
                    {"questiontype": "audio", "id": "clip", "src": "/a.ogg"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_audio", data)
    fields = q.fetch_fields()
    field_ids = [f.id for f in fields]
    assert field_ids == ["name", "clip_started", "clip_ended", "clip_listened"]
    by_id = {f.id: f.data_type for f in fields}
    assert by_id["clip_started"] == "float"
    assert by_id["clip_ended"] == "float"
    assert by_id["clip_listened"] == "float"


def test_fetch_fields_group_image_click_single_sub_expands_to_xy(tmp_path):
    """A single-click image_click sub-question fans out into _x/_y FLOAT
    columns inside a group, just like at top level."""
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "click_block",
                "questions": [
                    {
                        "questiontype": "image_click",
                        "id": "spot",
                        "src": "/m.png",
                    },
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_image_click", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["spot_x", "spot_y"]
    assert all(f.data_type == "float" for f in fields)


def test_fetch_fields_group_with_radiogrid_sub(tmp_path):
    """A radiogrid sub-question contributes its rows; its own parent id is
    structural and not a column (matches top-level radiogrid behavior)."""
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "scales_block",
                "questions": [
                    {
                        "questiontype": "radiogrid",
                        "id": "satisfaction",
                        "labels": ["1", "2", "3"],
                        "q_text": [
                            {"id": "sat_overall", "text": "Overall"},
                            {"id": "sat_speed", "text": "Speed"},
                        ],
                    }
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_radiogrid", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["sat_overall", "sat_speed"]
    assert "satisfaction" not in field_ids
    assert "scales_block" not in field_ids


def test_fetch_fields_group_textview_sub_produces_no_column(tmp_path):
    """Textview subs are allowed (for mid-group prose) but have no id and
    therefore contribute no columns."""
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "g",
                "questions": [
                    {"questiontype": "field", "id": "before"},
                    {"questiontype": "textview", "text": "Now the next part."},
                    {"questiontype": "field", "id": "after"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_textview_sub", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["before", "after"]


def test_fetch_fields_group_skips_nested_group_subs(tmp_path):
    """Validation rejects nested groups, but fetch_fields skips them
    defensively so a malformed JSON loaded directly via the API still
    produces a working column set."""
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "g",
                "questions": [
                    {"questiontype": "group", "id": "nested",
                     "questions": [{"questiontype": "field", "id": "x"}]},
                    {"questiontype": "field", "id": "kept"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_skip_nested", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["kept"]


def test_fetch_fields_top_level_and_group_share_flat_namespace(tmp_path):
    """Top-level questions and group sub-questions occupy a flat id namespace;
    the order of returned columns matches JSON traversal order."""
    data = {
        "questions": [
            {"questiontype": "field", "id": "intro"},
            {
                "questiontype": "group",
                "id": "block",
                "questions": [
                    {"questiontype": "field", "id": "a"},
                    {"questiontype": "num_field", "id": "b"},
                ],
            },
            {"questiontype": "field", "id": "outro"},
        ],
    }
    q = _write_questionnaire(tmp_path, "group_flat", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["intro", "a", "b", "outro"]


# ===========================================================================
# JSONQuestionnaire — question_type alias for questiontype
# ===========================================================================

def test_question_type_alias_top_level(tmp_path):
    data = {
        "questions": [
            {"question_type": "slider", "id": "s1"},
        ],
    }
    q = _write_questionnaire(tmp_path, "alias_top", data)
    fields = q.fetch_fields()
    assert [f.id for f in fields] == ["s1"]
    assert fields[0].data_type == "integer"
    # Alias is collapsed to the canonical key so downstream readers (templates,
    # validation, expression substitution) see only ``questiontype``.
    assert q.json_data["questions"][0]["questiontype"] == "slider"
    assert "question_type" not in q.json_data["questions"][0]


def test_question_type_alias_in_group_sub_questions(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "group",
                "id": "demographics",
                "questions": [
                    {"question_type": "field", "id": "first_name"},
                    {"question_type": "num_field", "id": "age"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "alias_group", data)
    field_ids = [f.id for f in q.fetch_fields()]
    assert field_ids == ["first_name", "age"]
    age_field = q.get_field("age")
    assert age_field.data_type == "integer"


def test_question_type_alias_matches_canonical_is_dropped(tmp_path):
    data = {
        "questions": [
            {"questiontype": "slider", "question_type": "slider", "id": "s1"},
        ],
    }
    q = _write_questionnaire(tmp_path, "alias_dup_match", data)
    q.fetch_fields()
    assert "question_type" not in q.json_data["questions"][0]
    assert q.json_data["questions"][0]["questiontype"] == "slider"


def test_string_encoded_int_attribute_is_coerced(tmp_path):
    """Numeric attributes declared as int (e.g. slider tick_count, default)
    accept stringly-typed JSON values."""
    data = {
        "questions": [
            {
                "questiontype": "slider",
                "id": "rating",
                "tick_count": "7",
                "default": "3",
                "width": "200",
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "string_int", data)
    q.fetch_fields()
    qd = q.json_data["questions"][0]
    assert qd["tick_count"] == 7 and isinstance(qd["tick_count"], int)
    assert qd["default"] == 3 and isinstance(qd["default"], int)
    assert qd["width"] == 200 and isinstance(qd["width"], int)


def test_string_encoded_float_attribute_is_coerced(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "audio",
                "id": "clip",
                "src": "/static/clip.mp3",
                "completion_threshold": "0.75",
            },
            {
                "questiontype": "num_field",
                "id": "score",
                "min": "0",
                "max": "100.5",
            },
        ],
    }
    q = _write_questionnaire(tmp_path, "string_float", data)
    q.fetch_fields()
    audio = q.json_data["questions"][0]
    nf = q.json_data["questions"][1]
    assert audio["completion_threshold"] == 0.75
    assert isinstance(audio["completion_threshold"], float)
    assert nf["min"] == 0.0 and isinstance(nf["min"], float)
    assert nf["max"] == 100.5 and isinstance(nf["max"], float)


@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("True", True), ("TRUE", True), ("  true  ", True),
    ("false", False), ("False", False), ("FALSE", False),
])
def test_string_encoded_bool_attribute_is_coerced(tmp_path, raw, expected):
    data = {
        "questions": [
            {
                "questiontype": "audio",
                "id": "clip",
                "src": "/static/clip.mp3",
                "autoplay": raw,
                "force_listen": raw,
            }
        ],
    }
    q = _write_questionnaire(tmp_path, f"string_bool_{raw.strip()}", data)
    q.fetch_fields()
    qd = q.json_data["questions"][0]
    assert qd["autoplay"] is expected
    assert qd["force_listen"] is expected


def test_invalid_string_for_int_raises(tmp_path):
    data = {
        "questions": [
            {"questiontype": "slider", "id": "s", "tick_count": "abc"},
        ],
    }
    path = tmp_path / "bad_int.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SyntaxError, match="tick_count"):
        JSONQuestionnaire(str(tmp_path), "bad_int", True)


def test_invalid_string_for_bool_raises(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "audio", "id": "a",
                "src": "/static/clip.mp3", "autoplay": "maybe",
            },
        ],
    }
    path = tmp_path / "bad_bool.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SyntaxError, match="autoplay"):
        JSONQuestionnaire(str(tmp_path), "bad_bool", True)


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("yes", True), ("YES", True), ("on", True),
    ("0", False), ("no", False), ("NO", False), ("off", False), ("", False),
])
def test_extended_bool_strings_match_jsontable_rules(tmp_path, raw, expected):
    data = {
        "questions": [
            {
                "questiontype": "audio", "id": "clip",
                "src": "/static/clip.mp3", "autoplay": raw,
            }
        ],
    }
    q = _write_questionnaire(tmp_path, f"ext_bool_{raw or 'empty'}", data)
    q.fetch_fields()
    assert q.json_data["questions"][0]["autoplay"] is expected


def test_native_typed_values_unchanged(tmp_path):
    """Coercion is a no-op when values already arrive as the right type."""
    data = {
        "questions": [
            {
                "questiontype": "slider", "id": "s",
                "tick_count": 5, "default": 2,
            },
            {
                "questiontype": "audio", "id": "a",
                "src": "/static/clip.mp3",
                "autoplay": True, "completion_threshold": 0.9,
            },
        ],
    }
    q = _write_questionnaire(tmp_path, "native_typed", data)
    q.fetch_fields()
    s, a = q.json_data["questions"]
    assert s["tick_count"] == 5 and a["autoplay"] is True
    assert a["completion_threshold"] == 0.9


def test_coercion_recurses_into_group_subquestions(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "group", "id": "g",
                "horizontal": "true",
                "questions": [
                    {
                        "questiontype": "slider", "id": "s",
                        "tick_count": "5",
                    },
                    {
                        "questiontype": "audio", "id": "a",
                        "src": "/static/clip.mp3",
                        "autoplay": "TRUE",
                    },
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "group_coerce", data)
    q.fetch_fields()
    g = q.json_data["questions"][0]
    assert g["horizontal"] is True
    assert g["questions"][0]["tick_count"] == 5
    assert g["questions"][1]["autoplay"] is True


def test_coercion_handles_checklist_item_text_entry_flags(tmp_path):
    data = {
        "questions": [
            {
                "questiontype": "checklist", "id": "checks",
                "questions": [
                    {
                        "id": "opt_a", "text": "A",
                        "text_entry": "true",
                        "text_entry_hides": "false",
                        "text_entry_width": "120",
                    },
                    {"id": "opt_b", "text": "B"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "checklist_coerce", data)
    q.fetch_fields()
    items = q.json_data["questions"][0]["questions"]
    assert items[0]["text_entry"] is True
    assert items[0]["text_entry_hides"] is False
    assert items[0]["text_entry_width"] == 120


def test_picture_select_value_is_not_coerced(tmp_path):
    """picture_select 'value' is intentionally polymorphic — the column
    type is derived from it, so coercion would change observable schema."""
    data = {
        "questions": [
            {
                "questiontype": "picture_select", "id": "ps",
                "images": [
                    {"src": "/a.png", "value": "1", "label": "A"},
                    {"src": "/b.png", "value": "2", "label": "B"},
                ],
            }
        ],
    }
    q = _write_questionnaire(tmp_path, "ps_no_coerce", data)
    fields = q.fetch_fields()
    assert fields[0].data_type == "string"  # values stayed strings
    images = q.json_data["questions"][0]["images"]
    assert images[0]["value"] == "1" and isinstance(images[0]["value"], str)


def test_question_type_alias_conflicts_with_canonical_raises(tmp_path):
    data = {
        "questions": [
            {"questiontype": "slider", "question_type": "num_field", "id": "x"},
        ],
    }
    path = tmp_path / "alias_conflict.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SyntaxError, match="question_type"):
        JSONQuestionnaire(str(tmp_path), "alias_conflict", True)


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
