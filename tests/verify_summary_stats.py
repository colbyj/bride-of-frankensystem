"""Standalone verification script for SummaryStats tests."""
import pandas as pd
from BOFS.admin.SummaryStats import SummaryStats


def test_basic_two_group_stats():
    df = pd.DataFrame({
        "condition": [1, 1, 1, 1, 2, 2, 2, 2],
        "score":     [2, 4, 6, 8, 10, 20, 30, 40],
    })
    grouped = df.groupby("condition")
    stats = SummaryStats(grouped, "score")

    g1 = pd.Series([2, 4, 6, 8], dtype=float)
    g2 = pd.Series([10, 20, 30, 40], dtype=float)

    assert stats.n == [4, 4], f"n: {stats.n}"
    assert stats.min == [g1.min(), g2.min()], f"min: {stats.min}"
    assert stats.max == [g1.max(), g2.max()], f"max: {stats.max}"
    assert abs(stats.mean[0] - g1.mean()) < 1e-9
    assert abs(stats.mean[1] - g2.mean()) < 1e-9
    assert abs(stats.median[0] - g1.median()) < 1e-9
    assert abs(stats.median[1] - g2.median()) < 1e-9
    assert abs(stats.std[0] - g1.std(ddof=1)) < 1e-9
    assert abs(stats.std[1] - g2.std(ddof=1)) < 1e-9
    assert abs(stats.sem[0] - g1.sem()) < 1e-9
    assert abs(stats.sem[1] - g2.sem()) < 1e-9
    assert abs(stats.var[0] - g1.var(ddof=1)) < 1e-9
    assert abs(stats.var[1] - g2.var(ddof=1)) < 1e-9
    print("PASS: test_basic_two_group_stats")


def test_single_group():
    df = pd.DataFrame({
        "group": ["A", "A", "A"],
        "value": [3.0, 7.0, 11.0],
    })
    grouped = df.groupby("group")
    stats = SummaryStats(grouped, "value")
    expected = pd.Series([3.0, 7.0, 11.0])

    assert stats.condition == ["A"]
    assert stats.n == [3]
    assert abs(stats.min[0] - expected.min()) < 1e-9
    assert abs(stats.max[0] - expected.max()) < 1e-9
    assert abs(stats.mean[0] - expected.mean()) < 1e-9
    assert abs(stats.median[0] - expected.median()) < 1e-9
    assert abs(stats.std[0] - expected.std(ddof=1)) < 1e-9
    assert abs(stats.sem[0] - expected.sem()) < 1e-9
    assert abs(stats.var[0] - expected.var(ddof=1)) < 1e-9
    print("PASS: test_single_group")


def test_condition_labels():
    df = pd.DataFrame({
        "arm":   ["Control", "Control", "Treatment", "Treatment"],
        "score": [1, 2, 3, 4],
    })
    grouped = df.groupby("arm")
    stats = SummaryStats(grouped, "score")
    assert stats.condition == ["Control", "Treatment"]
    print("PASS: test_condition_labels")


if __name__ == "__main__":
    test_basic_two_group_stats()
    test_single_group()
    test_condition_labels()
    print("ALL TESTS PASSED")
