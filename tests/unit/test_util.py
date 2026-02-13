"""Tests for pure utility functions in BOFS/util.py."""

import math

import pytest

from BOFS.util import (
    join_urls,
    fetch_attr,
    float_or_0,
    int_or_0,
    display_time,
    mean,
    variance,
    std,
    median,
)


# ---------------------------------------------------------------------------
# Helper objects for fetch_attr tests
# ---------------------------------------------------------------------------

class SimpleObj:
    def __init__(self):
        self.name = "alice"
        self.age = 30
        self.score = 0


class NestedObj:
    def __init__(self):
        self.child = SimpleObj()


class CallableAttrObj:
    def greeting(self):
        return "hello"

    def get_number(self):
        return 42


# =========================================================================
# join_urls
# =========================================================================

def test_join_urls_simple():
    assert join_urls("/base", "path") == "/base/path"


def test_join_urls_strips_leading_slash_from_subsequent_paths():
    assert join_urls("/base", "/path") == "/base/path"


def test_join_urls_multiple_segments():
    assert join_urls("/a", "/b", "/c") == "/a/b/c"


def test_join_urls_multiple_segments_no_leading_slashes():
    assert join_urls("/a", "b", "c") == "/a/b/c"


def test_join_urls_mixed_leading_slashes():
    assert join_urls("/a", "b", "/c") == "/a/b/c"


def test_join_urls_single_path():
    assert join_urls("/base") == "/base"


def test_join_urls_trailing_slash_preserved():
    assert join_urls("/base/", "path") == "/base/path"


def test_join_urls_no_base_slash():
    assert join_urls("base", "/path") == "base/path"


def test_join_urls_both_no_slashes():
    assert join_urls("base", "path") == "base/path"


# =========================================================================
# fetch_attr
# =========================================================================

def test_fetch_attr_simple_attribute():
    obj = SimpleObj()
    assert fetch_attr(obj, "name") == "alice"


def test_fetch_attr_numeric_attribute():
    obj = SimpleObj()
    assert fetch_attr(obj, "age") == 30


def test_fetch_attr_falsy_attribute():
    obj = SimpleObj()
    assert fetch_attr(obj, "score") == 0


def test_fetch_attr_missing_attribute_returns_none():
    obj = SimpleObj()
    assert fetch_attr(obj, "nonexistent") is None


def test_fetch_attr_nested_dotted_attribute():
    obj = NestedObj()
    assert fetch_attr(obj, "child.name") == "alice"


def test_fetch_attr_nested_dotted_missing_returns_none():
    obj = NestedObj()
    assert fetch_attr(obj, "child.missing") is None


def test_fetch_attr_callable_is_invoked():
    obj = CallableAttrObj()
    assert fetch_attr(obj, "greeting") == "hello"


def test_fetch_attr_callable_returns_number():
    obj = CallableAttrObj()
    assert fetch_attr(obj, "get_number") == 42


def test_fetch_attr_deeply_missing_returns_none():
    obj = NestedObj()
    assert fetch_attr(obj, "child.nonexistent.deep") is None


# =========================================================================
# float_or_0
# =========================================================================

def test_float_or_0_with_integer():
    assert float_or_0(5) == 5.0


def test_float_or_0_with_float():
    assert float_or_0(3.14) == pytest.approx(3.14)


def test_float_or_0_with_zero():
    assert float_or_0(0) == 0.0


def test_float_or_0_with_negative():
    assert float_or_0(-2.5) == pytest.approx(-2.5)


def test_float_or_0_with_nan_returns_zero():
    assert float_or_0(float("nan")) == 0.0


def test_float_or_0_with_numeric_string():
    assert float_or_0("3.14") == pytest.approx(3.14)


def test_float_or_0_with_string_nan():
    assert float_or_0("nan") == 0.0


def test_float_or_0_non_numeric_string_returns_zero():
    assert float_or_0("abc") == 0.0


def test_float_or_0_none_returns_zero():
    assert float_or_0(None) == 0.0


# =========================================================================
# int_or_0
# =========================================================================

def test_int_or_0_with_integer():
    assert int_or_0(7) == 7


def test_int_or_0_with_float():
    assert int_or_0(3.9) == 3  # int() truncates


def test_int_or_0_with_zero():
    assert int_or_0(0) == 0


def test_int_or_0_with_negative():
    assert int_or_0(-4) == -4


def test_int_or_0_with_numeric_string():
    assert int_or_0("42") == 42


def test_int_or_0_non_numeric_string_returns_zero():
    assert int_or_0("abc") == 0


def test_int_or_0_none_returns_zero():
    assert int_or_0(None) == 0


def test_int_or_0_float_string_returns_zero():
    assert int_or_0("3.14") == 0


def test_int_or_0_nan_float_returns_zero():
    assert int_or_0(float("nan")) == 0


# =========================================================================
# display_time
# =========================================================================

def test_display_time_zero_returns_zero():
    assert display_time(0) == 0


def test_display_time_none_returns_none():
    assert display_time(None) is None


def test_display_time_under_60_returns_integer_string():
    assert display_time(30) == "30"


def test_display_time_exactly_60():
    # 60 seconds is not > 60, so it falls to the else branch
    assert display_time(60) == "60"


def test_display_time_just_over_60():
    assert display_time(61) == "1:01"


def test_display_time_90_seconds():
    assert display_time(90) == "1:30"


def test_display_time_120_seconds():
    assert display_time(120) == "2:00"


def test_display_time_large_value():
    assert display_time(3661) == "61:01"


def test_display_time_one_second():
    assert display_time(1) == "1"


def test_display_time_59_seconds():
    assert display_time(59) == "59"


def test_display_time_fractional_under_60():
    assert display_time(45.7) == "45"


def test_display_time_fractional_over_60():
    # 75.5 / 60 = 1.258..., 75.5 % 60 = 15.5, int() truncates to 15
    assert display_time(75.5) == "1:15"


# =========================================================================
# mean
# =========================================================================

def test_mean_simple():
    assert mean([1, 2, 3]) == pytest.approx(2.0)


def test_mean_single_element():
    assert mean([5]) == pytest.approx(5.0)


def test_mean_floats():
    assert mean([1.5, 2.5, 3.5]) == pytest.approx(2.5)


def test_mean_negative_numbers():
    assert mean([-1, 0, 1]) == pytest.approx(0.0)


def test_mean_all_same():
    assert mean([4, 4, 4, 4]) == pytest.approx(4.0)


# =========================================================================
# variance
# =========================================================================

def test_variance_all_same():
    assert variance([5, 5, 5]) == pytest.approx(0.0)


def test_variance_single_element():
    assert variance([42]) == pytest.approx(0.0)


# =========================================================================
# std (stdev)
# =========================================================================

def test_std_all_same():
    assert std([5, 5, 5]) == pytest.approx(0.0)


def test_std_is_sqrt_of_variance():
    nums = [3, 7, 11, 2, 9]
    assert std(nums) == pytest.approx(math.sqrt(variance(nums)))


def test_std_single_element():
    assert std([100]) == pytest.approx(0.0)


# =========================================================================
# median
# =========================================================================

def test_median_odd_count():
    assert median([3, 1, 2]) == pytest.approx(2.0)


def test_median_even_count():
    assert median([1, 2, 3, 4]) == pytest.approx(2.5)


def test_median_single_element():
    assert median([7]) == pytest.approx(7.0)


def test_median_two_elements():
    assert median([1, 3]) == pytest.approx(2.0)


def test_median_already_sorted():
    assert median([1, 2, 3, 4, 5]) == pytest.approx(3.0)


def test_median_reverse_sorted():
    assert median([5, 4, 3, 2, 1]) == pytest.approx(3.0)


def test_median_with_duplicates():
    assert median([1, 1, 1, 1, 1]) == pytest.approx(1.0)


def test_median_negative_numbers():
    assert median([-5, -1, -3]) == pytest.approx(-3.0)
