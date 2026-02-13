"""Tests for SummaryStats from BOFS/admin/SummaryStats.py."""

import pytest
import pandas as pd
from BOFS.admin.SummaryStats import SummaryStats


def test_two_groups_with_known_values():
    df = pd.DataFrame({
        'group': [1, 1, 1, 1, 2, 2, 2, 2],
        'value': [10, 20, 30, 40, 50, 60, 70, 80]
    })
    grouped = df.groupby('group')
    stats = SummaryStats(grouped, 'value')

    assert stats.field_name == 'value'
    assert stats.condition == [1, 2]
    assert stats.n == [4, 4]
    assert stats.min == [10, 50]
    assert stats.max == [40, 80]
    assert stats.mean[0] == pytest.approx(25.0)
    assert stats.mean[1] == pytest.approx(65.0)
    assert stats.median[0] == pytest.approx(25.0)
    assert stats.median[1] == pytest.approx(65.0)
    # pandas uses sample std (ddof=1)
    assert stats.std[0] == pytest.approx(12.909944, rel=1e-4)
    assert stats.std[1] == pytest.approx(12.909944, rel=1e-4)
    assert stats.sem[0] == pytest.approx(6.454972, rel=1e-4)
    assert stats.sem[1] == pytest.approx(6.454972, rel=1e-4)
    assert stats.var[0] == pytest.approx(166.666667, rel=1e-4)
    assert stats.var[1] == pytest.approx(166.666667, rel=1e-4)


def test_single_group():
    df = pd.DataFrame({
        'condition': ['A', 'A', 'A', 'A', 'A'],
        'measurement': [5, 10, 15, 20, 25]
    })
    grouped = df.groupby('condition')
    stats = SummaryStats(grouped, 'measurement')

    assert stats.field_name == 'measurement'
    assert stats.condition == ['A']
    assert len(stats.n) == 1
    assert stats.n[0] == 5
    assert stats.min[0] == 5
    assert stats.max[0] == 25
    assert stats.mean[0] == pytest.approx(15.0)
    assert stats.median[0] == pytest.approx(15.0)


def test_string_condition_labels():
    df = pd.DataFrame({
        'condition': ['Control', 'Control', 'Control', 'Treatment', 'Treatment', 'Treatment'],
        'score': [100, 105, 95, 110, 115, 120]
    })
    grouped = df.groupby('condition')
    stats = SummaryStats(grouped, 'score')

    assert set(stats.condition) == {'Control', 'Treatment'}

    control_idx = stats.condition.index('Control')
    treatment_idx = stats.condition.index('Treatment')

    assert stats.n[control_idx] == 3
    assert stats.n[treatment_idx] == 3
    assert stats.mean[control_idx] == pytest.approx(100.0)
    assert stats.mean[treatment_idx] == pytest.approx(115.0)
