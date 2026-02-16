"""Tier 2 tests for JSONTable database methods.

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture and ``write_table_file()`` helper from conftest.py.
"""

import json

import pytest

from tests.conftest import write_table_file


# ===========================================================================
# Test data
# ===========================================================================

SIMPLE_TABLE = {
    "columns": {
        "score": {"type": "integer"},
        "label": {"type": "string"},
        "weight": {"type": "float"},
        "active": {"type": "boolean"},
    }
}

TABLE_WITH_EXPORTS = {
    "columns": {
        "score": {"type": "integer"},
        "label": {"type": "string"},
    },
    "exports": [
        {"fields": ["score", "label"], "format": "csv"},
    ],
}

TABLE_NO_EXPORTS = {
    "columns": {
        "score": {"type": "integer"},
    }
}


def _create_participant(app):
    p = app.db.Participant()
    p.mTurkID = ""
    p.ipAddress = ""
    p.userAgent = ""
    p.condition = 1
    p.finished = False
    app.db.session.add(p)
    app.db.session.commit()
    return p.participantID


# ===========================================================================
# TestCreateDBClass
# ===========================================================================

class TestCreateDBClass:
    def test_table_name(self, bofs_app):
        t = write_table_file(bofs_app, "events", SIMPLE_TABLE)
        assert t.db_class.__tablename__ == "table_events"

    def test_primary_key(self, bofs_app):
        t = write_table_file(bofs_app, "events", SIMPLE_TABLE)
        pk_col = t.db_class.__table__.c["eventsID"]
        assert pk_col.primary_key
        assert pk_col.autoincrement

    def test_participant_fk(self, bofs_app):
        t = write_table_file(bofs_app, "events", SIMPLE_TABLE)
        fk_col = t.db_class.__table__.c["participantID"]
        fk_targets = [fk.target_fullname for fk in fk_col.foreign_keys]
        assert "participant.participantID" in fk_targets

    def test_time_submitted_column(self, bofs_app):
        t = write_table_file(bofs_app, "events", SIMPLE_TABLE)
        table_cols = {c.name for c in t.db_class.__table__.c}
        assert "timeSubmitted" in table_cols

    def test_columns_from_json(self, bofs_app):
        t = write_table_file(bofs_app, "events", SIMPLE_TABLE)
        cols = {c.name: c for c in t.db_class.__table__.c}
        assert cols["score"].type.__class__.__name__ == "Integer"
        assert cols["label"].type.__class__.__name__ in ("Text", "TEXT")
        assert cols["weight"].type.__class__.__name__ == "Float"
        assert cols["active"].type.__class__.__name__ == "Boolean"


# ===========================================================================
# TestCreateExportsDict
# ===========================================================================

class TestCreateExportsDict:
    def test_no_exports_returns_none(self, bofs_app):
        t = write_table_file(bofs_app, "no_exp", TABLE_NO_EXPORTS)
        assert t.create_exports_dict() is None

    def test_exports_adds_table_key(self, bofs_app):
        t = write_table_file(bofs_app, "with_exp", TABLE_WITH_EXPORTS)
        exports = t.create_exports_dict()
        assert len(exports) == 1
        assert exports[0]["table"] == "with_exp"

    def test_preserves_fields(self, bofs_app):
        t = write_table_file(bofs_app, "with_exp2", TABLE_WITH_EXPORTS)
        exports = t.create_exports_dict()
        assert exports[0]["fields"] == ["score", "label"]
        assert exports[0]["format"] == "csv"


# ===========================================================================
# TestRowToDict
# ===========================================================================

class TestRowToDict:
    def _insert_row(self, app, t, pid, **values):
        obj = t.db_class()
        obj.participantID = pid
        for k, v in values.items():
            setattr(obj, k, v)
        app.db.session.add(obj)
        app.db.session.commit()
        return obj

    def test_integer_coercion(self, bofs_app):
        t = write_table_file(bofs_app, "coerce_int", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)
        row = self._insert_row(bofs_app, t, pid, score=42, label="x", weight=1.0, active=True)
        d = t.row_to_dict(row)
        assert d["score"] == 42
        assert isinstance(d["score"], int)

    def test_float_coercion(self, bofs_app):
        t = write_table_file(bofs_app, "coerce_float", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)
        row = self._insert_row(bofs_app, t, pid, score=1, label="x", weight=3.14, active=False)
        d = t.row_to_dict(row)
        assert d["weight"] == pytest.approx(3.14)
        assert isinstance(d["weight"], float)

    def test_string_coercion(self, bofs_app):
        t = write_table_file(bofs_app, "coerce_str", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)
        row = self._insert_row(bofs_app, t, pid, score=0, label="hello", weight=0.0, active=False)
        d = t.row_to_dict(row)
        assert d["label"] == "hello"
        assert isinstance(d["label"], str)


# ===========================================================================
# TestHandlePost
# ===========================================================================

class TestHandlePost:
    def test_creates_record_from_json(self, bofs_app):
        t = write_table_file(bofs_app, "post_json", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/post_json",
            method="POST",
            json={"score": 10, "label": "test", "weight": 2.5, "active": True},
            content_type="application/json",
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        assert rows[0].score == 10
        assert rows[0].label == "test"

    def test_creates_record_from_form(self, bofs_app):
        t = write_table_file(bofs_app, "post_form", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/post_form",
            method="POST",
            data={"score": "7", "label": "form_test", "weight": "1.5", "active": "True"},
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        assert rows[0].score == 7
        assert rows[0].label == "form_test"

    def test_type_coercion_on_post(self, bofs_app):
        t = write_table_file(bofs_app, "post_coerce", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/post_coerce",
            method="POST",
            data={"score": "99", "label": "coerced", "weight": "3.14", "active": "True"},
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert rows[0].score == 99
        assert isinstance(rows[0].score, int)
        assert rows[0].weight == pytest.approx(3.14)
