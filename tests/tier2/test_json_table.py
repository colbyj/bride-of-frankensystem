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

    def test_does_not_mutate_source_json_data(self, bofs_app):
        """Calling create_exports_dict should not annotate the source dicts.

        A second call must not see 'table' in the input definitions, and the
        original json_data structure should remain free of the injected key.
        """
        t = write_table_file(bofs_app, "with_exp3", TABLE_WITH_EXPORTS)

        first = t.create_exports_dict()
        assert "table" in first[0]
        # Source unaffected
        assert "table" not in t.json_data["exports"][0]

        # And a second call still produces a clean copy
        second = t.create_exports_dict()
        assert second[0]["table"] == "with_exp3"
        assert "table" not in t.json_data["exports"][0]
        # The two calls return independent dicts (not the same object)
        assert first[0] is not second[0]


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

    def test_datetime_returns_isoformat(self, bofs_app):
        """A datetime column should be serialised as an ISO-8601 string,
        not Python's default str(datetime) format."""
        from datetime import datetime as dt

        dt_table = {"columns": {"when": {"type": "datetime"}}}
        t = write_table_file(bofs_app, "dt_iso", dt_table)
        pid = _create_participant(bofs_app)

        target = dt(2026, 4, 27, 10, 30, 45)
        row = self._insert_row(bofs_app, t, pid, when=target)

        d = t.row_to_dict(row)
        assert d["when"] == "2026-04-27T10:30:45"
        assert isinstance(d["when"], str)


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

    def test_malformed_json_body_does_not_raise(self, bofs_app):
        """A POST with Content-Type: application/json but a malformed body
        should not raise — it falls through to the form-data path. This
        is a regression test for the bare ``except:`` → ``get_json(silent=True)``
        refactor."""
        t = write_table_file(bofs_app, "post_bad_json", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/post_bad_json",
            method="POST",
            data="this is not json",
            content_type="application/json",
        ):
            from flask import session
            session["participantID"] = pid
            # Must not raise. Behavior matches the previous bare-except
            # fallback: empty form data → row inserted with column defaults.
            result = t.handle_post()

        assert result == ("", 204)
        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1


# ===========================================================================
# TestBatchPost
# ===========================================================================

class TestBatchPost:
    def test_batch_insert_creates_n_rows(self, bofs_app):
        """A JSON list body inserts one row per element."""
        t = write_table_file(bofs_app, "batch_ok", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)

        payload = [
            {"score": 1, "label": "a", "weight": 0.1, "active": True},
            {"score": 2, "label": "b", "weight": 0.2, "active": False},
            {"score": 3, "label": "c", "weight": 0.3, "active": True},
        ]

        with bofs_app.test_request_context(
            "/table/batch_ok",
            method="POST",
            json=payload,
            content_type="application/json",
        ):
            from flask import session
            session["participantID"] = pid
            result = t.handle_post()

        assert result == ("", 204)
        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 3
        scores = sorted(r.score for r in rows)
        assert scores == [1, 2, 3]

    def test_batch_mixed_list_rolls_back(self, bofs_app):
        """A list containing a non-dict element must roll back — zero rows inserted."""
        from werkzeug.exceptions import HTTPException

        t = write_table_file(bofs_app, "batch_bad", SIMPLE_TABLE)
        pid = _create_participant(bofs_app)

        # First element is a valid dict; second is a bare string (invalid).
        payload = [{"score": 10, "label": "first"}, "not_a_dict"]

        with bofs_app.test_request_context(
            "/table/batch_bad",
            method="POST",
            json=payload,
            content_type="application/json",
        ):
            from flask import session
            session["participantID"] = pid
            with pytest.raises(HTTPException) as exc_info:
                t.handle_post()

        assert exc_info.value.code == 400
        # The session was rolled back — no rows should have been committed.
        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 0


# ===========================================================================
# TestJsonColumnType
# ===========================================================================

JSON_TABLE = {
    "columns": {
        "trial": {"type": "integer"},
        "events": {"type": "json"},
    }
}


class TestJsonColumnType:
    def test_json_column_round_trips_python_object(self, bofs_app):
        """A Python list sent via request.json is stored as JSON text and
        decoded back to a Python object by row_to_dict."""
        t = write_table_file(bofs_app, "json_roundtrip", JSON_TABLE)
        pid = _create_participant(bofs_app)

        events_payload = [{"t": 0, "x": 100, "y": 200}, {"t": 16, "x": 105, "y": 198}]

        with bofs_app.test_request_context(
            "/table/json_roundtrip",
            method="POST",
            json={"trial": 1, "events": events_payload},
            content_type="application/json",
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        d = t.row_to_dict(rows[0])
        assert d["events"] == events_payload
        assert isinstance(d["events"], list)

    def test_json_column_rejects_invalid_string_form_encoded(self, bofs_app):
        """An invalid JSON string sent form-encoded must return 400."""
        from werkzeug.exceptions import HTTPException

        t = write_table_file(bofs_app, "json_bad_str", JSON_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/json_bad_str",
            method="POST",
            data={"trial": "1", "events": "this is not json"},
        ):
            from flask import session
            session["participantID"] = pid
            with pytest.raises(HTTPException) as exc_info:
                t.handle_post()

        assert exc_info.value.code == 400
        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 0

    def test_json_column_accepts_valid_string_form_encoded(self, bofs_app):
        """A valid JSON string sent form-encoded is stored and round-trips correctly."""
        t = write_table_file(bofs_app, "json_good_str", JSON_TABLE)
        pid = _create_participant(bofs_app)

        events_list = [{"t": 0, "key": "A"}, {"t": 50, "key": "B"}]
        events_str = json.dumps(events_list)

        with bofs_app.test_request_context(
            "/table/json_good_str",
            method="POST",
            data={"trial": "1", "events": events_str},
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        d = t.row_to_dict(rows[0])
        assert d["events"] == events_list

    def test_json_column_null_when_not_provided(self, bofs_app):
        """row_to_dict returns None when the json column was never set."""
        t = write_table_file(bofs_app, "json_null", JSON_TABLE)
        pid = _create_participant(bofs_app)

        # Only send trial; omit events.
        with bofs_app.test_request_context(
            "/table/json_null",
            method="POST",
            json={"trial": 5},
            content_type="application/json",
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        d = t.row_to_dict(rows[0])
        assert d["events"] is None


# ===========================================================================
# TestBoolCoercion
# ===========================================================================

BOOL_TABLE = {
    "columns": {
        "flag": {"type": "boolean"},
    }
}


class TestBoolCoercion:
    def test_form_false_string_stored_as_false(self, bofs_app):
        """Form-encoded 'false' must be stored as False, not True."""
        t = write_table_file(bofs_app, "bool_false", BOOL_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/bool_false",
            method="POST",
            data={"flag": "false"},
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        assert rows[0].flag is False

    def test_form_zero_string_stored_as_false(self, bofs_app):
        """Form-encoded '0' must be stored as False."""
        t = write_table_file(bofs_app, "bool_zero", BOOL_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/bool_zero",
            method="POST",
            data={"flag": "0"},
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        assert rows[0].flag is False

    def test_form_true_string_stored_as_true(self, bofs_app):
        """Form-encoded 'true' must be stored as True."""
        t = write_table_file(bofs_app, "bool_true", BOOL_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/bool_true",
            method="POST",
            data={"flag": "true"},
        ):
            from flask import session
            session["participantID"] = pid
            t.handle_post()

        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 1
        assert rows[0].flag is True

    def test_garbage_bool_string_returns_400(self, bofs_app):
        """An unrecognised boolean string must abort with 400."""
        from werkzeug.exceptions import HTTPException

        t = write_table_file(bofs_app, "bool_garbage", BOOL_TABLE)
        pid = _create_participant(bofs_app)

        with bofs_app.test_request_context(
            "/table/bool_garbage",
            method="POST",
            data={"flag": "maybe"},
        ):
            from flask import session
            session["participantID"] = pid
            with pytest.raises(HTTPException) as exc_info:
                t.handle_post()

        assert exc_info.value.code == 400
        rows = bofs_app.db.session.query(t.db_class).all()
        assert len(rows) == 0
