"""Tier 2 tests for ``warn_about_orphan_participants``.

The check exists because SQLAlchemy can't enforce a foreign key across
engines. A partial restore (a researcher copies a stale ``main.db`` over
the current one, deletes one bind's file out of band, etc.) leaves rows
on the bound DB whose ``participantID`` is not present in the default
bind's ``participant`` table. The next signup that reuses that ID
silently inherits the orphan row's data — exactly the kind of failure
the warning is meant to surface at startup.
"""

import pytest

from BOFS.startup import warn_about_orphan_participants


def _capture_warnings(app):
    """Replace ``app.logger`` with a tiny capturing shim and return the
    list it writes into. Limited to ``.warning(...)`` because that's the
    only level the helper uses."""
    captured = []

    class _Capturing:
        def __init__(self, original):
            self._original = original
        def warning(self, fmt, *args):
            captured.append(fmt % args)
        def __getattr__(self, name):
            return getattr(self._original, name)

    app.logger = _Capturing(app.logger)
    return captured


def _make_participant(app, **kwargs):
    p = app.db.Participant()
    p.finished = True
    for k, v in kwargs.items():
        setattr(p, k, v)
    app.db.session.add(p)
    app.db.session.commit()
    return p


def _make_pii_row(app, participantID, email="alice@example.com"):
    CClass = app.questionnaires["contact"].db_class
    c = CClass()
    c.participantID = participantID
    c.tag = ""
    c.email = email
    app.db.session.add(c)
    app.db.session.commit()


class TestNoBinds:
    def test_silent_when_no_binds_configured(self, bofs_app):
        captured = _capture_warnings(bofs_app)
        warn_about_orphan_participants(bofs_app)
        assert captured == []


class TestNoOrphans:
    def test_clean_state_does_not_warn(self, bofs_app_for_export_with_binds):
        app = bofs_app_for_export_with_binds
        p = _make_participant(app)
        _make_pii_row(app, p.participantID)

        captured = _capture_warnings(app)
        warn_about_orphan_participants(app)
        assert captured == []

    def test_empty_bind_table_does_not_warn(self, bofs_app_for_export_with_binds):
        app = bofs_app_for_export_with_binds
        # Participant exists but no PII row yet — common during a study
        # that hasn't reached the contact page yet.
        _make_participant(app)
        captured = _capture_warnings(app)
        warn_about_orphan_participants(app)
        assert captured == []


class TestOrphanDetected:
    def test_orphan_pii_row_triggers_warning(self, bofs_app_for_export_with_binds):
        """The scenario we're guarding against: a contact row exists for a
        participantID that no longer (or never did) exist on the default
        bind. The warning must name the table, the bind, and the IDs."""
        app = bofs_app_for_export_with_binds
        # No matching Participant row — insert directly into the pii bind.
        _make_pii_row(app, participantID=9999)

        captured = _capture_warnings(app)
        warn_about_orphan_participants(app)
        assert len(captured) == 1
        msg = captured[0]
        assert "questionnaire_contact" in msg
        assert "'pii'" in msg
        assert "9999" in msg

    def test_warning_message_explains_the_hazard(
        self, bofs_app_for_export_with_binds
    ):
        """The message has to spell out the actual risk (ID reuse leaking
        old data into a new participant) — otherwise a researcher who
        sees it might dismiss it as a benign mismatch."""
        app = bofs_app_for_export_with_binds
        _make_pii_row(app, participantID=42)

        captured = _capture_warnings(app)
        warn_about_orphan_participants(app)
        assert "inherit" in captured[0].lower() or "reuse" in captured[0].lower()

    def test_caps_sample_for_many_orphans(self, bofs_app_for_export_with_binds):
        """When the entire bind is orphaned (full restore mismatch), the
        warning must not dump every ID into the log — show a sample plus a
        count of how many more are present."""
        app = bofs_app_for_export_with_binds
        for pid in range(1, 51):  # 50 orphans
            _make_pii_row(app, participantID=pid, email=f"u{pid}@example.com")

        captured = _capture_warnings(app)
        warn_about_orphan_participants(app)
        assert len(captured) == 1
        msg = captured[0]
        assert "50 row" in msg or "50 rows" in msg
        # Sample limit is 10; remaining count should be 40.
        assert "+40 more" in msg

    def test_only_orphans_listed_not_valid_rows(
        self, bofs_app_for_export_with_binds
    ):
        """When some rows are valid and some are orphans, the warning
        names only the orphan IDs."""
        app = bofs_app_for_export_with_binds
        p = _make_participant(app)  # participantID = 1
        _make_pii_row(app, participantID=p.participantID)  # valid
        _make_pii_row(app, participantID=999)  # orphan

        captured = _capture_warnings(app)
        warn_about_orphan_participants(app)
        assert len(captured) == 1
        msg = captured[0]
        assert "999" in msg
        # The valid participant's ID could appear inside larger numbers,
        # so use a more specific shape — message should report 1 row.
        assert "1 row" in msg


class TestCustomTableOnBind:
    """Cross-bind tables defined via JSONTable should also be scanned for
    orphans, not only questionnaires."""

    def test_table_orphan_triggers_warning(self, tmp_path):
        """A JSONTable on the pii bind with an orphan participantID row
        should trigger the warning just like a questionnaire does."""
        # Build a fresh fixture with a JSONTable on pii (the standard
        # fixtures only register questionnaires there).
        import json
        import os
        import toml
        from BOFS.create_app import create_app

        q_dir = tmp_path / "questionnaires"
        q_dir.mkdir()
        (q_dir / "experiment.json").write_text(json.dumps({
            "title": "Experiment",
            "questions": [{"questiontype": "field", "id": "score"}],
        }), encoding="utf-8")

        tables_dir = tmp_path / "tables"
        tables_dir.mkdir()
        (tables_dir / "pii_log.json").write_text(json.dumps({
            "database": "pii",
            "columns": {"value": {"type": "string"}},
        }), encoding="utf-8")

        (tmp_path / "consent.html").write_text("<p>OK</p>", encoding="utf-8")

        config_path = tmp_path / "config.toml"
        config_path.write_text(toml.dumps({
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"pii": "sqlite:///:memory:"},
            "SECRET_KEY": "test-key",
            "TITLE": "T",
            "ADMIN_PASSWORD": "test",
            "USE_ADMIN": False,
            "BRUTE_FORCE_PROTECTION": False,
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        }), encoding="utf-8")

        original_cwd = os.getcwd()
        app = create_app(str(tmp_path), str(config_path), debug=False)
        try:
            with app.app_context():
                # Insert an orphan row in the pii-bind table.
                TClass = app.tables["pii_log"].db_class
                row = TClass()
                row.participantID = 7777
                row.value = "leaked"
                app.db.session.add(row)
                app.db.session.commit()

                captured = _capture_warnings(app)
                warn_about_orphan_participants(app)
                assert len(captured) == 1
                msg = captured[0]
                assert "table_pii_log" in msg
                assert "'pii'" in msg
                assert "7777" in msg
        finally:
            os.chdir(original_cwd)
