"""Tier 2 tests for the per-bind startup warnings emitted by BOFS.

* ``warn_about_unused_binds`` — a bind that no questionnaire/table references
  is almost certainly a typo or stale config.
* ``warn_about_orphan_participants`` — covered in
  ``test_bind_orphan_warning.py``. Splitting it out keeps this file pure
  (no DB context required) and lets the orphan tests use real engines.

Warnings (not errors) so a researcher mid-setup or using a bind
programmatically in a custom blueprint isn't blocked from running the app.
"""

from types import SimpleNamespace

import pytest

from BOFS.startup import warn_about_unused_binds


def _fake_app(binds=None, questionnaires=None, tables=None):
    """Build a tiny app-shaped object with just enough state for the
    warning helpers to run, plus a captured logger that records the calls.
    """
    captured = []

    class _CapturingLogger:
        def warning(self, fmt, *args):
            captured.append(fmt % args)

    return SimpleNamespace(
        config={"SQLALCHEMY_BINDS": binds or {}},
        questionnaires=questionnaires or {},
        tables=tables or {},
        logger=_CapturingLogger(),
    ), captured


class TestUnusedBindsWarning:
    def test_warns_when_no_questionnaire_uses_bind(self):
        app, captured = _fake_app(binds={"pii": "sqlite:///pii.db"})
        warn_about_unused_binds(app)
        assert len(captured) == 1
        assert "pii" in captured[0]

    def test_does_not_warn_when_questionnaire_uses_bind(self):
        q = SimpleNamespace(bind_key="pii")
        app, captured = _fake_app(
            binds={"pii": "sqlite:///pii.db"},
            questionnaires={"contact": q},
        )
        warn_about_unused_binds(app)
        assert captured == []

    def test_does_not_warn_when_table_uses_bind(self):
        t = SimpleNamespace(bind_key="pii")
        app, captured = _fake_app(
            binds={"pii": "sqlite:///pii.db"},
            tables={"contact_log": t},
        )
        warn_about_unused_binds(app)
        assert captured == []

    def test_warns_only_for_unused_binds_in_mixed_config(self):
        used_q = SimpleNamespace(bind_key="pii")
        app, captured = _fake_app(
            binds={
                "pii": "sqlite:///pii.db",
                "archive": "sqlite:///archive.db",  # nobody references this
            },
            questionnaires={"contact": used_q},
        )
        warn_about_unused_binds(app)
        assert len(captured) == 1
        assert "archive" in captured[0]
        assert "pii" not in captured[0]

    def test_no_binds_no_warnings(self):
        app, captured = _fake_app()
        warn_about_unused_binds(app)
        assert captured == []
