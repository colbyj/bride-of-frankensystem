"""Tests for pure functions in BOFS/admin/util.py."""

import pytest
import decimal
import datetime
from BOFS.admin.util import (
    escape_csv,
    questionnaire_name_and_tag,
    remove_non_ascii,
    alchemy_encoder,
    _datetime_convert,
)


# =========================================================================
# _datetime_convert
# =========================================================================

def test_datetime_convert_basic():
    dt = datetime.datetime(2025, 2, 6, 14, 30, 45)
    assert _datetime_convert(dt) == "2025-02-06 14:30:45"


def test_datetime_convert_midnight():
    dt = datetime.datetime(2024, 1, 1, 0, 0, 0)
    assert _datetime_convert(dt) == "2024-01-01 00:00:00"


# =========================================================================
# remove_non_ascii
# =========================================================================

def test_remove_non_ascii_only_ascii():
    result = remove_non_ascii("hello world")
    assert result == b"hello world"


def test_remove_non_ascii_with_unicode():
    result = remove_non_ascii("hello caf\u00e9")
    assert result == b"hello caf"


def test_remove_non_ascii_special_chars():
    result = remove_non_ascii("test!@#$%^&*()")
    assert result == b"test!@#$%^&*()"


def test_remove_non_ascii_empty_string():
    result = remove_non_ascii("")
    assert result == b""


# =========================================================================
# alchemy_encoder
# =========================================================================

def test_alchemy_encoder_date():
    d = datetime.date(2025, 2, 6)
    assert alchemy_encoder(d) == "2025-02-06"


def test_alchemy_encoder_datetime():
    dt = datetime.datetime(2025, 2, 6, 14, 30, 45)
    assert alchemy_encoder(dt) == "2025-02-06T14:30:45"


def test_alchemy_encoder_decimal():
    dec = decimal.Decimal("123.456")
    result = alchemy_encoder(dec)
    assert result == 123.456
    assert isinstance(result, float)


def test_alchemy_encoder_decimal_zero():
    assert alchemy_encoder(decimal.Decimal("0")) == 0.0


def test_alchemy_encoder_decimal_negative():
    assert alchemy_encoder(decimal.Decimal("-99.99")) == -99.99


# =========================================================================
# escape_csv
# =========================================================================

def test_escape_csv_string_basic():
    assert escape_csv("hello") == '"hello"'


def test_escape_csv_string_with_quotes():
    assert escape_csv('say "hi"') == '"say \'hi\'"'


def test_escape_csv_string_with_newlines():
    assert escape_csv("hello\nworld") == '"hello world"'


def test_escape_csv_string_with_carriage_returns():
    assert escape_csv("hello\rworld") == '"hello world"'


def test_escape_csv_string_strips_whitespace():
    assert escape_csv("  hello world  ") == '"hello world"'


def test_escape_csv_none():
    assert escape_csv(None) == ""


def test_escape_csv_bool_true():
    assert escape_csv(True) == "1"


def test_escape_csv_bool_false():
    assert escape_csv(False) == "0"


def test_escape_csv_integer():
    assert escape_csv(42) == "42"


def test_escape_csv_float():
    assert escape_csv(3.14) == "3.14"


# =========================================================================
# questionnaire_name_and_tag
# =========================================================================

def test_questionnaire_name_and_tag_with_tag():
    name, tag = questionnaire_name_and_tag("survey/v1")
    assert name == "survey"
    assert tag == "v1"


def test_questionnaire_name_and_tag_without_tag():
    name, tag = questionnaire_name_and_tag("survey")
    assert name == "survey"
    assert tag == ""


def test_questionnaire_name_and_tag_empty_tag():
    name, tag = questionnaire_name_and_tag("survey/")
    assert name == "survey"
    assert tag == ""


def test_questionnaire_name_and_tag_multiple_slashes():
    name, tag = questionnaire_name_and_tag("survey/v1/extra")
    assert name == "survey"
    assert tag == "v1"
