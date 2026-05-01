"""Tests for pure functions in BOFS/admin/util.py."""

import pytest
import decimal
import datetime
from BOFS.admin.util import (
    csv_string,
    formula_safe,
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
# formula_safe
# =========================================================================

def test_formula_safe_passes_normal_strings_through():
    assert formula_safe("hello") == "hello"
    assert formula_safe("") == ""
    assert formula_safe("123abc") == "123abc"


def test_formula_safe_prefixes_equals():
    assert formula_safe("=SUM(A1:A10)") == "'=SUM(A1:A10)"


def test_formula_safe_prefixes_plus():
    assert formula_safe("+1") == "'+1"


def test_formula_safe_prefixes_minus():
    assert formula_safe("-2+3") == "'-2+3"


def test_formula_safe_prefixes_at():
    assert formula_safe("@SUM") == "'@SUM"


def test_formula_safe_prefixes_tab():
    assert formula_safe("\tcmd") == "'\tcmd"


def test_formula_safe_passes_non_strings_through():
    # Non-strings keep their type so csv.writer can handle them.
    assert formula_safe(42) == 42
    assert formula_safe(None) is None
    assert formula_safe(True) is True


# =========================================================================
# csv_string
# =========================================================================

def test_csv_string_basic_row():
    out = csv_string([["a", "b", "c"]])
    assert out == "a,b,c\n"


def test_csv_string_quotes_cells_with_commas():
    out = csv_string([["has,comma", "fine"]])
    assert out == '"has,comma",fine\n'


def test_csv_string_doubles_internal_quotes():
    # RFC 4180: a quote inside a quoted cell is doubled.
    out = csv_string([['say "hi"']])
    assert out == '"say ""hi"""\n'


def test_csv_string_quotes_cells_with_newlines():
    out = csv_string([["a\nb"]])
    assert out == '"a\nb"\n'


def test_csv_string_none_renders_empty():
    out = csv_string([[None, "x"]])
    assert out == ",x\n"


def test_csv_string_bool_renders_as_1_or_0():
    assert csv_string([[True, False]]) == "1,0\n"


def test_csv_string_numeric_passes_through():
    assert csv_string([[42, 3.14]]) == "42,3.14\n"


def test_csv_string_applies_formula_safe():
    out = csv_string([["=cmd|'/c calc'!A1"]])
    # Leading = is prefixed with ', then the whole cell is quoted by csv.writer
    # (the prefix introduces no special chars but the original = sigil is gone).
    assert out == "'=cmd|'/c calc'!A1\n"


def test_csv_string_multiple_rows():
    out = csv_string([["h1", "h2"], ["a", "b"], ["c", "d"]])
    assert out == "h1,h2\na,b\nc,d\n"


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
