"""Tier 2 tests for per-questionnaire / per-table database bindings.

Covers the model-construction path: when a JSON file declares
``"database": "<bind>"``, the dynamically-built model class must end up on
the named engine, drop the cross-engine FK and the ``participant`` backref,
and not be created on the default engine.
"""

import pytest
from sqlalchemy import inspect as sa_inspect

from tests.conftest import write_questionnaire_file, write_table_file


# ===========================================================================
# Default-bind (regression guard)
# ===========================================================================

class TestDefaultBindUnchanged:
    """Questionnaires/tables with no ``database`` field must look exactly
    like they did before the per-bind work — same FK, same backref, no
    ``__bind_key__`` attribute."""

    def test_questionnaire_has_no_bind_key(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "default_q", {
            "questions": [{"questiontype": "field", "id": "name"}],
        })
        # Either the attribute is absent or it's None — both mean "default".
        assert getattr(q.db_class, "__bind_key__", None) is None
        assert q.bind_key is None

    def test_questionnaire_keeps_fk_and_relationship(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "fk_q", {
            "questions": [{"questiontype": "field", "id": "name"}],
        })
        pid_col = q.db_class.__table__.c.participantID
        assert len(pid_col.foreign_keys) == 1
        fk = next(iter(pid_col.foreign_keys))
        assert fk.target_fullname == "participant.participantID"
        # Backref still works
        assert "participant" in q.db_class.__mapper__.relationships

    def test_table_keeps_fk_and_relationship(self, bofs_app):
        t = write_table_file(bofs_app, "default_t", {
            "columns": {"value": {"type": "integer"}},
        })
        pid_col = t.db_class.__table__.c.participantID
        assert len(pid_col.foreign_keys) == 1
        assert "participant" in t.db_class.__mapper__.relationships


# ===========================================================================
# Cross-bind models
# ===========================================================================

class TestCrossBindQuestionnaire:
    def test_bind_key_is_set(self, bofs_app_with_binds):
        q = write_questionnaire_file(bofs_app_with_binds, "pii_q", {
            "database": "pii",
            "questions": [{"questiontype": "field", "id": "email"}],
        })
        assert q.bind_key == "pii"
        assert q.db_class.__bind_key__ == "pii"

    def test_fk_is_dropped(self, bofs_app_with_binds):
        q = write_questionnaire_file(bofs_app_with_binds, "no_fk_q", {
            "database": "pii",
            "questions": [{"questiontype": "field", "id": "email"}],
        })
        pid_col = q.db_class.__table__.c.participantID
        assert len(pid_col.foreign_keys) == 0
        # Indexed so Participant.questionnaire() lookups stay cheap
        assert pid_col.index is True

    def test_participant_relationship_omitted(self, bofs_app_with_binds):
        q = write_questionnaire_file(bofs_app_with_binds, "no_rel_q", {
            "database": "pii",
            "questions": [{"questiontype": "field", "id": "email"}],
        })
        assert "participant" not in q.db_class.__mapper__.relationships

    def test_table_created_on_correct_engine(self, bofs_app_with_binds):
        write_questionnaire_file(bofs_app_with_binds, "where_q", {
            "database": "pii",
            "questions": [{"questiontype": "field", "id": "email"}],
        })
        # Re-run create_all so the model is materialised on the pii engine
        bofs_app_with_binds.db.create_all()

        pii_tables = sa_inspect(
            bofs_app_with_binds.db.engines["pii"]
        ).get_table_names()
        default_tables = sa_inspect(
            bofs_app_with_binds.db.engine
        ).get_table_names()

        assert "questionnaire_where_q" in pii_tables
        assert "questionnaire_where_q" not in default_tables
        # Participant stays on the default bind regardless of any per-bind config
        assert "participant" in default_tables
        assert "participant" not in pii_tables


class TestCrossBindTable:
    def test_bind_key_is_set(self, bofs_app_with_binds):
        t = write_table_file(bofs_app_with_binds, "pii_t", {
            "database": "pii",
            "columns": {"value": {"type": "integer"}},
        })
        assert t.bind_key == "pii"
        assert t.db_class.__bind_key__ == "pii"

    def test_fk_dropped_relationship_omitted(self, bofs_app_with_binds):
        t = write_table_file(bofs_app_with_binds, "no_fk_t", {
            "database": "pii",
            "columns": {"value": {"type": "integer"}},
        })
        pid_col = t.db_class.__table__.c.participantID
        assert len(pid_col.foreign_keys) == 0
        assert pid_col.index is True
        assert "participant" not in t.db_class.__mapper__.relationships

    def test_table_lives_on_pii_engine(self, bofs_app_with_binds):
        write_table_file(bofs_app_with_binds, "where_t", {
            "database": "pii",
            "columns": {"value": {"type": "integer"}},
        })
        bofs_app_with_binds.db.create_all()

        pii_tables = sa_inspect(
            bofs_app_with_binds.db.engines["pii"]
        ).get_table_names()
        default_tables = sa_inspect(
            bofs_app_with_binds.db.engine
        ).get_table_names()

        assert "table_where_t" in pii_tables
        assert "table_where_t" not in default_tables
