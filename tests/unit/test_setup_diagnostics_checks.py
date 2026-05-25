"""Unit tests for the post-load (cross-file) validation passes added
to surface common researcher mistakes that the per-file validators
can't see on their own.

Covers:

* ``validate_questionnaire_not_empty``
* ``validate_table_not_empty``
* ``validate_image_assets`` (with on-disk fixture files)
* ``validate_page_list_show_if_refs`` (cross-questionnaire scope)
* ``validate_calculations`` upgrade — AST-based; tolerates cross-calc
  references within the same questionnaire
"""

import os
from types import SimpleNamespace

import pytest

from BOFS.PageList import PageList
from BOFS.validation import (
    validate_calculations,
    validate_image_assets,
    validate_page_list_show_if_refs,
    validate_table_not_empty,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _q(json_data):
    """Build a minimal questionnaire stand-in for the validators (they
    read ``json_data`` and ``fetch_fields`` only)."""
    fields = []
    for q in json_data.get("questions", []) or []:
        if isinstance(q, dict) and "id" in q:
            fields.append(SimpleNamespace(id=q["id"]))
    obj = SimpleNamespace(json_data=json_data)
    obj.fetch_fields = lambda: fields
    return obj


def _t(json_data):
    return SimpleNamespace(json_data=json_data)


# ---------------------------------------------------------------------------
# Empty-questionnaire / empty-table checks
# ---------------------------------------------------------------------------


class TestEmptyTable:
    def test_no_columns_key_warns(self):
        results = validate_table_not_empty(_t({}), "empty")
        assert len(results) == 1
        assert "no columns" in results[0].message

    def test_empty_columns_dict_warns(self):
        results = validate_table_not_empty(_t({"columns": {}}), "empty")
        assert len(results) == 1

    def test_one_column_clean(self):
        results = validate_table_not_empty(
            _t({"columns": {"x": {"type": "integer"}}}), "ok",
        )
        assert results == []


# ---------------------------------------------------------------------------
# Image asset existence
# ---------------------------------------------------------------------------


class TestImageAssets:
    def test_existing_static_asset_clean(self, tmp_path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "foo.png").write_bytes(b"PNG-bytes")
        q = _q({
            "questions": [
                {"questiontype": "image_select",
                 "images": [{"src": "/static/foo.png", "value": "a"}]},
            ],
        })
        results = validate_image_assets(
            q, "with_assets", str(tmp_path), bofs_path=str(tmp_path / "bofs")
        )
        assert results == []

    def test_missing_static_asset_warns(self, tmp_path):
        q = _q({
            "questions": [
                {"questiontype": "image_select",
                 "images": [{"src": "/static/missing.png", "value": "a"}]},
            ],
        })
        results = validate_image_assets(
            q, "missing", str(tmp_path), bofs_path=str(tmp_path / "bofs")
        )
        assert len(results) == 1
        assert "missing.png" in results[0].message
        assert results[0].severity == "warning"

    def test_image_click_src_checked(self, tmp_path):
        q = _q({
            "questions": [
                {"questiontype": "image_click", "id": "x",
                 "src": "/static/map.png"},
            ],
        })
        results = validate_image_assets(
            q, "ic", str(tmp_path), bofs_path=str(tmp_path / "bofs")
        )
        assert len(results) == 1
        assert "map.png" in results[0].message

    def test_external_url_skipped(self, tmp_path):
        q = _q({
            "questions": [
                {"questiontype": "image_click", "id": "x",
                 "src": "https://cdn.example.com/img.png"},
            ],
        })
        results = validate_image_assets(
            q, "ext", str(tmp_path), bofs_path=str(tmp_path / "bofs")
        )
        assert results == []

    def test_bofs_static_resolves_in_bundled_path(self, tmp_path):
        bofs_root = tmp_path / "bofs"
        (bofs_root / "static").mkdir(parents=True)
        (bofs_root / "static" / "shared.png").write_bytes(b"x")
        q = _q({
            "questions": [
                {"questiontype": "image_select",
                 "images": [{"src": "/BOFS_static/shared.png", "value": "a"}]},
            ],
        })
        results = validate_image_assets(
            q, "bofs_static", str(tmp_path), bofs_path=str(bofs_root)
        )
        assert results == []


# ---------------------------------------------------------------------------
# Cross-questionnaire page_list show_if reference check
# ---------------------------------------------------------------------------


def _build_page_list(raw):
    """Compile a raw PAGE_LIST into the shape with ``_show_if_ast`` /
    ``_show_if_refs`` attached, the same way BOFSFlask does at startup."""
    return PageList(raw).page_list


class TestPageListShowIfRefs:
    def test_known_bare_field_clean(self):
        questionnaires = {
            "intake": _q({"questions": [
                {"questiontype": "field", "id": "age"},
            ]}),
        }
        page_list = _build_page_list([
            {"name": "Survey", "path": "questionnaire/survey",
             "show_if": "age >= 18"},
        ])
        results = validate_page_list_show_if_refs(
            page_list, questionnaires, tables={}
        )
        assert results == []

    def test_unknown_bare_field_warns(self):
        questionnaires = {
            "intake": _q({"questions": [
                {"questiontype": "field", "id": "age"},
            ]}),
        }
        page_list = _build_page_list([
            {"name": "Survey", "path": "questionnaire/survey",
             "show_if": "agee >= 18"},
        ])
        results = validate_page_list_show_if_refs(
            page_list, questionnaires, tables={}
        )
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert "agee" in results[0].message

    def test_reserved_participant_names_clean(self):
        page_list = _build_page_list([
            {"name": "X", "path": "questionnaire/x",
             "show_if": "condition == 1 and source == 'prolific'"},
        ])
        results = validate_page_list_show_if_refs(page_list, {}, tables={})
        assert results == []

    def test_dotted_questionnaire_field_clean(self):
        questionnaires = {
            "intake": _q({"questions": [
                {"questiontype": "field", "id": "age"},
            ]}),
        }
        page_list = _build_page_list([
            {"name": "Survey", "path": "questionnaire/survey",
             "show_if": "intake.age >= 18"},
        ])
        results = validate_page_list_show_if_refs(
            page_list, questionnaires, tables={}
        )
        assert results == []

    def test_dotted_unknown_questionnaire_warns(self):
        page_list = _build_page_list([
            {"name": "Survey", "path": "questionnaire/survey",
             "show_if": "nope.age >= 18"},
        ])
        results = validate_page_list_show_if_refs(page_list, {}, tables={})
        assert len(results) == 1
        assert "nope" in results[0].message

    def test_dotted_unknown_field_warns(self):
        questionnaires = {
            "intake": _q({"questions": [
                {"questiontype": "field", "id": "age"},
            ]}),
        }
        page_list = _build_page_list([
            {"name": "Survey", "path": "questionnaire/survey",
             "show_if": "intake.years >= 18"},
        ])
        results = validate_page_list_show_if_refs(
            page_list, questionnaires, tables={}
        )
        assert len(results) == 1
        assert "years" in results[0].message
        assert "intake" in results[0].message

    def test_conditional_routing_arm_show_if_checked(self):
        page_list = _build_page_list([
            {"name": "Branch", "path": "questionnaire/branch",
             "conditional_routing": [
                 {"condition": 1, "show_if": "phantom > 0",
                  "page_list": [
                      {"name": "Y", "path": "questionnaire/y"},
                  ]},
             ]},
        ])
        results = validate_page_list_show_if_refs(page_list, {}, tables={})
        assert any("phantom" in r.message for r in results)


# ---------------------------------------------------------------------------
# validate_calculations upgrade: AST-based, calc-cross-references allowed
# ---------------------------------------------------------------------------


class TestCalculationsCrossRef:
    def test_calc_referencing_another_calc_clean(self):
        json_data = {
            "questions": [
                {"questiontype": "field", "id": "a"},
                {"questiontype": "field", "id": "b"},
            ],
            "participant_calculations": {
                "sum_ab": "a + b",
                "doubled": "sum_ab * 2",
            },
        }
        results = validate_calculations(json_data, "calc_q")
        assert results == []

    def test_calc_referencing_unknown_field_warns(self):
        json_data = {
            "questions": [
                {"questiontype": "field", "id": "a"},
            ],
            "participant_calculations": {
                "bad": "a + zzz",
            },
        }
        results = validate_calculations(json_data, "calc_q")
        # The unknown reference appears as a warning, not an error.
        warnings = [r for r in results if r.severity == "warning"]
        assert any("zzz" in r.message for r in warnings)

    def test_calc_using_safe_function_clean(self):
        json_data = {
            "questions": [
                {"questiontype": "field", "id": "x"},
                {"questiontype": "field", "id": "y"},
            ],
            "participant_calculations": {
                "avg_xy": "mean([x, y])",
            },
        }
        results = validate_calculations(json_data, "calc_q")
        warnings = [r for r in results if r.severity == "warning"]
        assert warnings == []
