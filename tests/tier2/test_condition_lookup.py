"""Tier 2 tests for ConditionLookupService.

Tests cover CSV/DB source loading, startup validation, lookup hits/misses, and
the assign_condition integration that promotes a miss into ConditionLookupMiss.
All tests use the ``bofs_app`` fixture; per-test config is primed by mutating
``app.config`` and re-running ``ConditionLookupService.init_app(app)``.
"""

import os

import pytest
from sqlalchemy import create_engine, text

from BOFS.services.condition_lookup import (
    ConditionLookupConfigError,
    ConditionLookupMiss,
    ConditionLookupService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_participant(app, **kwargs):
    defaults = dict(
        mTurkID="",
        ipAddress="127.0.0.1",
        userAgent="test-agent",
        condition=0,
        finished=False,
        excludeFromCount=False,
    )
    defaults.update(kwargs)
    p = app.db.Participant()
    for k, v in defaults.items():
        setattr(p, k, v)
    app.db.session.add(p)
    app.db.session.commit()
    return p


def _write_csv(tmp_path, name, rows, header="id,condition"):
    """Write a CSV file under tmp_path. *rows* is a list of (id, condition) tuples."""
    path = tmp_path / name
    lines = [header]
    for row in rows:
        lines.append(",".join(str(c) for c in row))
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _make_prior_db(tmp_path, name, rows):
    """Create a SQLite file with a participant table populated from *rows*.

    rows: list of dicts with keys mTurkID, condition, finished (defaults provided).
    """
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE participant ("
            "  participantID INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  mTurkID TEXT,"
            "  condition INTEGER,"
            "  finished BOOLEAN"
            ")"
        ))
        for row in rows:
            conn.execute(
                text("INSERT INTO participant (mTurkID, condition, finished) "
                     "VALUES (:m, :c, :f)"),
                {"m": row["mTurkID"], "c": row["condition"],
                 "f": row.get("finished", False)},
            )
    engine.dispose()
    return f"sqlite:///{path}"


def _prime(app, csv_path=None, db_uri=None):
    """Set the config keys and re-run init_app to refresh cached state."""
    app.config["CONDITIONS_FROM_CSV"] = csv_path
    app.config["CONDITIONS_FROM_DB"] = db_uri
    ConditionLookupService.init_app(app)


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

class TestCsvValidation:
    def test_missing_file_errors(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        with pytest.raises(ConditionLookupConfigError, match="does not exist"):
            _prime(bofs_app, csv_path=str(tmp_path / "nope.csv"))

    def test_empty_file_errors(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}]
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ConditionLookupConfigError, match="empty"):
            _prime(bofs_app, csv_path=str(path))

    def test_non_integer_condition_errors(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "bad.csv", [("alice", "one")])
        with pytest.raises(ConditionLookupConfigError, match="not an integer"):
            _prime(bofs_app, csv_path=path)

    def test_out_of_range_condition_errors(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "oor.csv", [("alice", "5")])
        with pytest.raises(ConditionLookupConfigError, match="out of range"):
            _prime(bofs_app, csv_path=path)

    def test_duplicate_id_conflicting_conditions_errors(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "dup.csv",
                          [("alice", "1"), ("alice", "2")])
        with pytest.raises(ConditionLookupConfigError, match="appears twice"):
            _prime(bofs_app, csv_path=path)

    def test_duplicate_id_same_condition_ok(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "dup_ok.csv",
                          [("alice", "1"), ("alice", "1")])
        _prime(bofs_app, csv_path=path)
        assert ConditionLookupService.lookup("alice") == 1

    def test_blank_lines_ignored(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = tmp_path / "with_blanks.csv"
        path.write_text("id,condition\nalice,1\n\n\nbob,2\n", encoding="utf-8")
        _prime(bofs_app, csv_path=str(path))
        assert ConditionLookupService.lookup("alice") == 1
        assert ConditionLookupService.lookup("bob") == 2


class TestDbValidation:
    def test_unreachable_db_errors(self, bofs_app, tmp_path):
        bogus = f"sqlite:///{tmp_path / 'does_not_exist.db'}"
        # Engine creation succeeds for sqlite, but probing the participant table fails.
        with pytest.raises(ConditionLookupConfigError, match="participant"):
            _prime(bofs_app, db_uri=bogus)

    def test_missing_required_columns_errors(self, bofs_app, tmp_path):
        path = tmp_path / "wrong_schema.db"
        engine = create_engine(f"sqlite:///{path}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE participant (id INTEGER)"))
        engine.dispose()
        with pytest.raises(ConditionLookupConfigError, match="participant"):
            _prime(bofs_app, db_uri=f"sqlite:///{path}")


# ---------------------------------------------------------------------------
# Runtime lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_no_source_configured_is_not_configured(self, bofs_app):
        _prime(bofs_app)
        assert ConditionLookupService.is_configured() is False
        assert ConditionLookupService.lookup("alice") is None

    def test_csv_hit(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1"), ("bob", "2")])
        _prime(bofs_app, csv_path=path)

        assert ConditionLookupService.is_configured() is True
        assert ConditionLookupService.lookup("alice") == 1
        assert ConditionLookupService.lookup("bob") == 2

    def test_csv_miss_returns_none(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        _prime(bofs_app, csv_path=path)

        assert ConditionLookupService.lookup("eve") is None

    def test_csv_strips_whitespace(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        _prime(bofs_app, csv_path=path)

        assert ConditionLookupService.lookup("  alice  ") == 1

    def test_db_hit(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "alice", "condition": 2, "finished": True},
        ])
        _prime(bofs_app, db_uri=db_uri)

        assert ConditionLookupService.lookup("alice") == 2

    def test_db_prefers_finished_attempt(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        # Two rows for the same ID: an unfinished condition 1, finished condition 2.
        # Should pick the finished one regardless of insertion order.
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "alice", "condition": 1, "finished": False},
            {"mTurkID": "alice", "condition": 2, "finished": True},
        ])
        _prime(bofs_app, db_uri=db_uri)

        assert ConditionLookupService.lookup("alice") == 2

    def test_db_skips_zero_condition(self, bofs_app, tmp_path):
        """Consent-only abandons (condition=0) shouldn't be picked up."""
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "alice", "condition": 0, "finished": False},
        ])
        _prime(bofs_app, db_uri=db_uri)

        assert ConditionLookupService.lookup("alice") is None

    def test_db_miss_returns_none(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "alice", "condition": 1, "finished": True},
        ])
        _prime(bofs_app, db_uri=db_uri)

        assert ConditionLookupService.lookup("eve") is None

    def test_csv_takes_precedence_over_db(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "alice", "condition": 2, "finished": True},
        ])
        _prime(bofs_app, csv_path=path, db_uri=db_uri)

        assert ConditionLookupService.lookup("alice") == 1

    def test_db_used_when_csv_misses(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "bob", "condition": 2, "finished": True},
        ])
        _prime(bofs_app, csv_path=path, db_uri=db_uri)

        assert ConditionLookupService.lookup("bob") == 2

    def test_empty_external_id_returns_none(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        _prime(bofs_app, csv_path=path)

        assert ConditionLookupService.lookup("") is None
        assert ConditionLookupService.lookup(None) is None


class TestFindPriorParticipant:
    def test_returns_full_row(self, bofs_app, tmp_path):
        db_uri = _make_prior_db(tmp_path, "prior.db", [
            {"mTurkID": "alice", "condition": 2, "finished": True},
        ])
        _prime(bofs_app, db_uri=db_uri)

        row = ConditionLookupService.find_prior_participant("alice")
        assert row is not None
        assert row["mTurkID"] == "alice"
        assert row["condition"] == 2
        assert "participantID" in row

    def test_returns_none_when_no_db_configured(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        _prime(bofs_app, csv_path=path)  # CSV only, no DB

        assert ConditionLookupService.find_prior_participant("alice") is None


# ---------------------------------------------------------------------------
# Integration with Participant.assign_condition
# ---------------------------------------------------------------------------

class TestAssignConditionIntegration:
    def test_lookup_hit_sets_condition_without_balancer(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True
        path = _write_csv(tmp_path, "c.csv", [("alice", "2")])
        _prime(bofs_app, csv_path=path)

        # Seed the balancer skewed toward condition 1 — if lookup is honored,
        # the participant should still land in condition 2.
        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=1)

        p = _make_participant(bofs_app, mTurkID="alice", condition=0)
        p.assign_condition()
        bofs_app.db.session.commit()

        assert p.condition == 2

    def test_lookup_miss_raises(self, bofs_app, tmp_path):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        _prime(bofs_app, csv_path=path)

        p = _make_participant(bofs_app, mTurkID="eve", condition=0)
        with pytest.raises(ConditionLookupMiss) as exc_info:
            p.assign_condition()
        assert exc_info.value.external_id == "eve"

    def test_no_source_configured_falls_through_to_balancer(self, bofs_app):
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True
        _prime(bofs_app)  # no CSV, no DB

        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=1)

        p = _make_participant(bofs_app, mTurkID="anyone", condition=0)
        p.assign_condition()
        bofs_app.db.session.commit()

        # Balancer picks the under-represented condition.
        assert p.condition == 2

    def test_empty_mturk_id_falls_through_to_balancer_even_with_source(
        self, bofs_app, tmp_path
    ):
        """A participant who hasn't entered an external ID yet should still
        get a balancer assignment — the lookup only kicks in once we know who
        they are. (Relevant for /consent before /external_id flows.)"""
        bofs_app.config["CONDITIONS"] = [{"label": "A"}, {"label": "B"}]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True
        path = _write_csv(tmp_path, "c.csv", [("alice", "1")])
        _prime(bofs_app, csv_path=path)

        _make_participant(bofs_app, condition=1)

        p = _make_participant(bofs_app, mTurkID="", condition=0)
        p.assign_condition()
        bofs_app.db.session.commit()

        # No mTurkID yet → balancer runs → picks condition 2 (count 0 vs 1).
        assert p.condition == 2
