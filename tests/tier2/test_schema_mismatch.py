"""
Integration tests for database-vs-JSON schema mismatch detection and auto-fix.

Tests the full flow: questionnaire JSON changes after data has been collected,
orphaned columns are detected, made nullable, and new inserts succeed.
"""

import json
import os

import pytest
from sqlalchemy import inspect as sa_inspect, text

from tests.conftest import write_questionnaire_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_row(app, q, participant_id, tag="", **field_values):
    """Insert a questionnaire row directly via the ORM."""
    from BOFS.util import utcnow_naive

    obj = q.db_class()
    obj.participantID = participant_id
    obj.tag = tag
    obj.timeStarted = utcnow_naive()
    obj.timeEnded = utcnow_naive()
    for k, v in field_values.items():
        setattr(obj, k, v)
    app.db.session.add(obj)
    app.db.session.commit()
    return obj


def _create_participant(app):
    """Create a minimal participant and return their ID."""
    p = app.db.Participant()
    p.condition = 1
    app.db.session.add(p)
    app.db.session.commit()
    return p.participantID


def _reload_questionnaire(app, name, new_json):
    """
    Simulate a researcher changing a questionnaire JSON and restarting.

    Writes new JSON, creates a new JSONQuestionnaire, runs create_db_class
    (which will reflect the existing table and detect orphans), then
    replaces the old questionnaire in the app.
    """
    from BOFS.JSONQuestionnaire import JSONQuestionnaire

    q_dir = os.path.join(app.root_path, "questionnaires")
    filepath = os.path.join(q_dir, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(new_json, f)

    # Remove old table from SQLAlchemy's in-memory metadata so we can re-define it.
    # The actual DB table remains — we're only clearing the Python-side registration.
    table_name = f"questionnaire_{name}"
    if table_name in app.db.metadata.tables:
        app.db.metadata.remove(app.db.metadata.tables[table_name])

    q_new = JSONQuestionnaire(q_dir, name, is_in_db=True)
    q_new.create_db_class()

    # Replace in the app's registry
    app.questionnaires[name] = q_new
    setattr(app.db, "Questionnaire" + q_new.db_class.__name__, q_new.db_class)

    return q_new


# ---------------------------------------------------------------------------
# Orphaned column detection
# ---------------------------------------------------------------------------

class TestOrphanedColumnDetection:
    """Test that create_db_class() detects columns in DB but not in JSON."""

    def test_no_orphans_on_fresh_table(self, bofs_app):
        """First-time creation has no orphaned columns."""
        q = write_questionnaire_file(bofs_app, "fresh", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })
        assert q._orphaned_columns == []
        assert q._type_mismatches == []

    def test_detects_renamed_field(self, bofs_app):
        """Renaming q1→q1_new should detect q1 as orphaned."""
        # Original questionnaire with q1
        q = write_questionnaire_file(bofs_app, "rename_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        # Reload with q1 renamed to q1_new
        q_new = _reload_questionnaire(bofs_app, "rename_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1_new"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        orphaned_names = [c['name'] for c in q_new._orphaned_columns]
        assert "q1" in orphaned_names
        assert "q1_new" not in orphaned_names
        assert "q2" not in orphaned_names

    def test_detects_removed_field(self, bofs_app):
        """Removing a field entirely should detect it as orphaned."""
        q = write_questionnaire_file(bofs_app, "remove_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "slider", "id": "q2"},
                {"questiontype": "field", "id": "q3"},
            ]
        })

        q_new = _reload_questionnaire(bofs_app, "remove_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        orphaned_names = [c['name'] for c in q_new._orphaned_columns]
        assert "q2" in orphaned_names
        assert "q3" in orphaned_names
        assert "q1" not in orphaned_names

    def test_detects_removed_group_sub_field(self, bofs_app):
        """Removing a sub-question from a group should leave its column
        orphaned, just like removing a top-level question."""
        write_questionnaire_file(bofs_app, "group_orphan", {
            "questions": [
                {
                    "questiontype": "group",
                    "id": "demographics",
                    "questions": [
                        {"questiontype": "field", "id": "first_name"},
                        {"questiontype": "num_field", "id": "age"},
                    ],
                }
            ]
        })

        q_new = _reload_questionnaire(bofs_app, "group_orphan", {
            "questions": [
                {
                    "questiontype": "group",
                    "id": "demographics",
                    "questions": [
                        {"questiontype": "field", "id": "first_name"},
                    ],
                }
            ]
        })

        orphaned_names = [c['name'] for c in q_new._orphaned_columns]
        assert "age" in orphaned_names
        assert "first_name" not in orphaned_names
        # The group's own id was never a column, so it's not orphaned either.
        assert "demographics" not in orphaned_names

    def test_standard_columns_not_flagged(self, bofs_app):
        """Standard columns (participantID, tag, etc.) should never be flagged."""
        q = write_questionnaire_file(bofs_app, "standard_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        # Reload with all fields removed
        q_new = _reload_questionnaire(bofs_app, "standard_test", {
            "questions": [
                {"questiontype": "textview", "title": "Info only"},
            ]
        })

        orphaned_names = [c['name'] for c in q_new._orphaned_columns]
        # q1 is orphaned, but standard columns should not be
        assert "q1" in orphaned_names
        assert "participantID" not in orphaned_names
        assert "tag" not in orphaned_names
        assert "timeStarted" not in orphaned_names
        assert "timeEnded" not in orphaned_names


# ---------------------------------------------------------------------------
# Type mismatch detection
# ---------------------------------------------------------------------------

class TestTypeMismatchDetection:
    """Test that create_db_class() detects column type changes."""

    def test_detects_integer_to_text(self, bofs_app):
        """Changing a slider (integer) to a field (text) should flag a mismatch."""
        q = write_questionnaire_file(bofs_app, "type_test", {
            "questions": [
                {"questiontype": "slider", "id": "rating"},
            ]
        })

        q_new = _reload_questionnaire(bofs_app, "type_test", {
            "questions": [
                {"questiontype": "field", "id": "rating"},
            ]
        })

        assert len(q_new._type_mismatches) == 1
        assert q_new._type_mismatches[0]['field_id'] == 'rating'
        assert q_new._type_mismatches[0]['db_type'] == 'INTEGER'
        assert q_new._type_mismatches[0]['json_type'] == 'string'

    def test_no_mismatch_when_types_match(self, bofs_app):
        """Same type should not flag a mismatch."""
        q = write_questionnaire_file(bofs_app, "same_type", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        q_new = _reload_questionnaire(bofs_app, "same_type", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        assert q_new._type_mismatches == []


# ---------------------------------------------------------------------------
# Table reconstruction (make_columns_nullable)
# ---------------------------------------------------------------------------

class TestMakeColumnsNullable:
    """Test that orphaned columns can be made nullable via table reconstruction."""

    def test_orphaned_column_becomes_nullable(self, bofs_app):
        """After make_columns_nullable, the orphaned column should be nullable."""
        from BOFS.admin.util import make_columns_nullable

        q = write_questionnaire_file(bofs_app, "nullable_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        # q1 should be NOT NULL initially
        inspector = sa_inspect(bofs_app.db.engine)
        cols = {c['name']: c for c in inspector.get_columns("questionnaire_nullable_test")}
        assert cols['q1']['nullable'] is False

        # Make q1 nullable
        result = make_columns_nullable("questionnaire_nullable_test", ["q1"])
        assert result is True

        # Verify q1 is now nullable
        inspector = sa_inspect(bofs_app.db.engine)
        cols = {c['name']: c for c in inspector.get_columns("questionnaire_nullable_test")}
        assert cols['q1']['nullable'] is True
        # q2 should still be NOT NULL
        assert cols['q2']['nullable'] is False

    def test_preserves_existing_data(self, bofs_app):
        """Table reconstruction should not lose any existing data."""
        from BOFS.admin.util import make_columns_nullable

        q = write_questionnaire_file(bofs_app, "preserve_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        pid = _create_participant(bofs_app)
        _insert_row(bofs_app, q, pid, q1=42, q2="hello")

        make_columns_nullable("questionnaire_preserve_test", ["q1"])

        # Verify data is still there
        with bofs_app.db.engine.connect() as conn:
            row = conn.execute(text("SELECT q1, q2 FROM questionnaire_preserve_test")).fetchone()
        assert row[0] == 42
        assert row[1] == "hello"

    def test_noop_when_already_nullable(self, bofs_app):
        """If columns are already nullable, no reconstruction needed."""
        from BOFS.admin.util import make_columns_nullable

        write_questionnaire_file(bofs_app, "noop_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        # First make it nullable
        make_columns_nullable("questionnaire_noop_test", ["q1"])
        # Second call should be a no-op
        result = make_columns_nullable("questionnaire_noop_test", ["q1"])
        assert result is False

    def test_noop_for_empty_list(self, bofs_app):
        """Empty column list should be a no-op."""
        from BOFS.admin.util import make_columns_nullable

        write_questionnaire_file(bofs_app, "empty_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        result = make_columns_nullable("questionnaire_empty_test", [])
        assert result is False


# ---------------------------------------------------------------------------
# New column added as nullable (check_and_add_column without default)
# ---------------------------------------------------------------------------

class TestNullableNewColumns:
    """Test that new columns added without a default are nullable."""

    def test_new_column_is_nullable(self, bofs_app):
        """A column added via check_and_add_column() without default should be nullable."""
        from BOFS.admin.util import check_and_add_column

        write_questionnaire_file(bofs_app, "newcol_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        # Add a new column without default
        check_and_add_column("questionnaire_newcol_test", "q_new", "TEXT")

        inspector = sa_inspect(bofs_app.db.engine)
        cols = {c['name']: c for c in inspector.get_columns("questionnaire_newcol_test")}
        assert "q_new" in cols
        # Column should be nullable (no NOT NULL in DDL)
        assert cols['q_new']['nullable'] is True

    def test_existing_rows_have_null_for_new_column(self, bofs_app):
        """Existing rows should have NULL for a newly added nullable column."""
        from BOFS.admin.util import check_and_add_column

        q = write_questionnaire_file(bofs_app, "null_rows_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        pid = _create_participant(bofs_app)
        _insert_row(bofs_app, q, pid, q1=10)

        # Add new column
        check_and_add_column("questionnaire_null_rows_test", "q_new", "INTEGER")

        with bofs_app.db.engine.connect() as conn:
            row = conn.execute(text("SELECT q1, q_new FROM questionnaire_null_rows_test")).fetchone()
        assert row[0] == 10
        assert row[1] is None

    def test_system_column_still_gets_default(self, bofs_app):
        """System columns with explicit defaults should still use the default."""
        from BOFS.admin.util import check_and_add_column

        # Add a column with a default (system column pattern)
        check_and_add_column("participant", "test_sys_col", "BOOLEAN", 0)

        inspector = sa_inspect(bofs_app.db.engine)
        cols = {c['name']: c for c in inspector.get_columns("participant")}
        assert "test_sys_col" in cols


# ---------------------------------------------------------------------------
# End-to-end: renamed field, new insert succeeds
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """Full scenario: rename field, make nullable, insert new row."""

    def test_renamed_field_new_insert_succeeds(self, bofs_app):
        """After renaming a field, new inserts should succeed with NULL for the old column."""
        from BOFS.admin.util import make_columns_nullable, check_and_add_column

        # Step 1: Create questionnaire with q1, create participants, insert data
        # (Create both participants before reload to avoid backref conflicts)
        q = write_questionnaire_file(bofs_app, "e2e_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })
        pid1 = _create_participant(bofs_app)
        pid2 = _create_participant(bofs_app)
        _insert_row(bofs_app, q, pid1, q1=5, q2="original")

        # Step 2: Researcher renames q1 → q1_new in JSON
        q_new = _reload_questionnaire(bofs_app, "e2e_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1_new"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        # Step 3: Make orphaned columns nullable (as create_app would do)
        orphaned_names = [c['name'] for c in q_new._orphaned_columns]
        assert "q1" in orphaned_names
        make_columns_nullable("questionnaire_e2e_test", orphaned_names)

        # Step 4: Add the new column (as check_and_add_column would do)
        check_and_add_column("questionnaire_e2e_test", "q1_new", "INTEGER")

        # Step 5: Insert a new row via raw SQL — should succeed
        with bofs_app.db.engine.connect() as conn:
            conn.execute(text(
                'INSERT INTO questionnaire_e2e_test '
                '(participantID, tag, timeStarted, timeEnded, q1_new, q2) '
                "VALUES (:pid, '', datetime('now'), datetime('now'), 10, 'new')"
            ), {"pid": pid2})
            conn.commit()

        # Step 6: Verify both rows
        with bofs_app.db.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT participantID, q1, q1_new, q2 FROM questionnaire_e2e_test ORDER BY participantID"
            )).fetchall()

        assert len(rows) == 2
        # Old row: q1=5, q1_new=NULL, q2="original"
        assert rows[0][1] == 5       # q1 has original data
        assert rows[0][2] is None    # q1_new didn't exist yet
        assert rows[0][3] == "original"
        # New row: q1=NULL, q1_new=10, q2="new"
        assert rows[1][1] is None    # q1 is orphaned, NULL
        assert rows[1][2] == 10      # q1_new has new data
        assert rows[1][3] == "new"


# ---------------------------------------------------------------------------
# validate_db_schema() unit-level (but needs app context for questionnaire)
# ---------------------------------------------------------------------------

class TestValidateDbSchema:
    """Test the validation warning generation."""

    def test_notice_for_orphaned_columns(self, bofs_app):
        """Orphaned columns are surfaced as info-level notices: BOFS
        preserves the existing data and writes NULL for new submissions,
        so nothing is broken — the researcher is just informed."""
        from BOFS.validation import validate_db_schema

        q = write_questionnaire_file(bofs_app, "warn_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
                {"questiontype": "field", "id": "q2"},
            ]
        })

        q_new = _reload_questionnaire(bofs_app, "warn_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        results = validate_db_schema(q_new, "warn_test")
        assert len(results) == 1
        assert results[0].severity == "info"
        assert "q2" in results[0].message
        assert "no longer defined" in results[0].message

    def test_warnings_for_type_mismatches(self, bofs_app):
        """Type mismatches should produce warnings."""
        from BOFS.validation import validate_db_schema

        q = write_questionnaire_file(bofs_app, "type_warn", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        q_new = _reload_questionnaire(bofs_app, "type_warn", {
            "questions": [
                {"questiontype": "field", "id": "q1"},
            ]
        })

        warnings = validate_db_schema(q_new, "type_warn")
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"
        assert "q1" in warnings[0].message
        assert "INTEGER" in warnings[0].message

    def test_no_warnings_when_clean(self, bofs_app):
        """No warnings when JSON matches DB."""
        from BOFS.validation import validate_db_schema

        q = write_questionnaire_file(bofs_app, "clean_test", {
            "questions": [
                {"questiontype": "slider", "id": "q1"},
            ]
        })

        warnings = validate_db_schema(q, "clean_test")
        assert len(warnings) == 0

    def test_no_warnings_without_attributes(self):
        """A questionnaire without _orphaned_columns attribute returns empty."""
        from BOFS.validation import validate_db_schema

        class FakeQ:
            pass

        warnings = validate_db_schema(FakeQ(), "fake")
        assert len(warnings) == 0
