"""Tests for JSONTableColumn from BOFS/JSONTable.py."""

import datetime
import pytest
from BOFS.JSONTable import JSONTableColumn


# --- Constructor: data type assignment ---

def test_integer_type():
    col = JSONTableColumn("age", {"type": "integer"})
    assert col.name == "age"
    assert col.data_type == "integer"
    assert col.default == 0


def test_float_type():
    col = JSONTableColumn("score", {"type": "float"})
    assert col.name == "score"
    assert col.data_type == "float"
    assert col.default == 0


def test_datetime_type():
    col = JSONTableColumn("created_at", {"type": "datetime"})
    assert col.name == "created_at"
    assert col.data_type == "datetime"
    assert col.default == datetime.datetime.min


def test_boolean_type():
    col = JSONTableColumn("is_active", {"type": "boolean"})
    assert col.name == "is_active"
    assert col.data_type == "boolean"
    assert col.default is False


def test_string_type():
    col = JSONTableColumn("label", {"type": "string"})
    assert col.name == "label"
    assert col.data_type == "string"
    assert col.default == ""


# --- Constructor: edge cases ---

def test_unknown_type_falls_back_to_string():
    col = JSONTableColumn("mystery", {"type": "blob"})
    assert col.data_type == "string"
    assert col.default == ""


def test_missing_type_key_leaves_defaults():
    col = JSONTableColumn("no_type", {"description": "irrelevant"})
    assert col.data_type == ""
    assert col.default == ""


def test_custom_default_overrides_builtin():
    col = JSONTableColumn("count", {"type": "integer", "default": 42})
    assert col.data_type == "integer"
    assert col.default == 42


def test_custom_default_on_boolean():
    col = JSONTableColumn("flag", {"type": "boolean", "default": True})
    assert col.data_type == "boolean"
    assert col.default is True


# --- get_type_ddl ---

@pytest.mark.parametrize("type_str, expected_ddl", [
    ("integer", "INTEGER"),
    ("float", "NUMERIC"),
    ("datetime", "DATETIME"),
    ("boolean", "BOOLEAN"),
    ("string", "TEXT"),
    ("blob", "TEXT"),
])
def test_get_type_ddl(type_str, expected_ddl):
    col = JSONTableColumn("col", {"type": type_str})
    assert col.get_type_ddl() == expected_ddl


def test_get_type_ddl_when_no_type_provided():
    """When no 'type' key is given, data_type is empty string, DDL falls through to TEXT."""
    col = JSONTableColumn("col", {})
    assert col.get_type_ddl() == "TEXT"
