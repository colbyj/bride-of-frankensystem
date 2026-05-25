"""Tier 2 tests for the per-bind startup notices emitted by BOFS.

* ``warn_about_unused_binds`` — a bind that no questionnaire/table
  references could be a typo, or could be a bind used programmatically
  in a custom blueprint. Surfaced as info-level so a real typo is
  visible without flagging legitimate use.
* ``warn_about_orphan_participants`` — covered in
  ``test_bind_orphan_warning.py``. Splitting it out keeps this file pure
  (no DB context required) and lets the orphan tests use real engines.
"""

from types import SimpleNamespace

import pytest

from BOFS.setup_diagnostics import DiagnosticCollector
from BOFS.startup import warn_about_unused_binds


def _fake_app(binds=None, questionnaires=None, tables=None):
    """Build a tiny app-shaped object with just enough state for the
    warning helpers to run, plus a real DiagnosticCollector that records
    every diagnostic.
    """

    class _NullLogger:
        def info(self, *_a, **_k): pass
        def warning(self, *_a, **_k): pass
        def error(self, *_a, **_k): pass

    app = SimpleNamespace(
        config={"SQLALCHEMY_BINDS": binds or {}},
        questionnaires=questionnaires or {},
        tables=tables or {},
        logger=_NullLogger(),
    )
    app.setup_diagnostics = DiagnosticCollector(app)
    return app


class TestUnusedBindsWarning:
    def test_notice_emitted_when_no_questionnaire_uses_bind(self):
        app = _fake_app(binds={"pii": "sqlite:///pii.db"})
        warn_about_unused_binds(app)
        diags = app.setup_diagnostics.by_severity("info")
        assert len(diags) == 1
        assert "pii" in diags[0].message
        assert diags[0].category == "bind"

    def test_no_notice_when_questionnaire_uses_bind(self):
        q = SimpleNamespace(bind_key="pii")
        app = _fake_app(
            binds={"pii": "sqlite:///pii.db"},
            questionnaires={"contact": q},
        )
        warn_about_unused_binds(app)
        assert list(app.setup_diagnostics) == []

    def test_no_notice_when_table_uses_bind(self):
        t = SimpleNamespace(bind_key="pii")
        app = _fake_app(
            binds={"pii": "sqlite:///pii.db"},
            tables={"contact_log": t},
        )
        warn_about_unused_binds(app)
        assert list(app.setup_diagnostics) == []

    def test_notice_only_for_unused_binds_in_mixed_config(self):
        used_q = SimpleNamespace(bind_key="pii")
        app = _fake_app(
            binds={
                "pii": "sqlite:///pii.db",
                "archive": "sqlite:///archive.db",  # nobody references this
            },
            questionnaires={"contact": used_q},
        )
        warn_about_unused_binds(app)
        diags = app.setup_diagnostics.by_severity("info")
        assert len(diags) == 1
        assert "archive" in diags[0].message
        assert "pii" not in diags[0].message

    def test_no_binds_no_notice(self):
        app = _fake_app()
        warn_about_unused_binds(app)
        assert list(app.setup_diagnostics) == []
