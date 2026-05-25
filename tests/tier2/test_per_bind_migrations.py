"""Tier 2 tests for bind-aware migration helpers in BOFS.admin.util."""

import pytest
from sqlalchemy import inspect as sa_inspect, text

from BOFS.admin.util import check_and_add_column, make_columns_nullable
from tests.conftest import write_questionnaire_file


class TestCheckAndAddColumnPerBind:
    def test_adds_to_named_bind_only(self, bofs_app_with_binds):
        # Create a cross-bind questionnaire so the pii engine has the table
        write_questionnaire_file(bofs_app_with_binds, "pii_target", {
            "database": "pii",
            "questions": [{"questiontype": "field", "id": "email"}],
        })
        bofs_app_with_binds.db.create_all()

        added = check_and_add_column(
            "questionnaire_pii_target", "extra", "TEXT", bind_key="pii"
        )
        assert added is True

        pii_cols = {
            c["name"]
            for c in sa_inspect(bofs_app_with_binds.db.engines["pii"]).get_columns(
                "questionnaire_pii_target"
            )
        }
        assert "extra" in pii_cols

        # The default engine doesn't even have this table, so the column is
        # definitionally not on it; participant on the default engine is
        # untouched.
        default_participant_cols = {
            c["name"] for c in sa_inspect(bofs_app_with_binds.db.engine).get_columns(
                "participant"
            )
        }
        assert "extra" not in default_participant_cols

    def test_idempotent_on_named_bind(self, bofs_app_with_binds):
        write_questionnaire_file(bofs_app_with_binds, "idem_q", {
            "database": "pii",
            "questions": [{"questiontype": "field", "id": "email"}],
        })
        bofs_app_with_binds.db.create_all()

        assert check_and_add_column(
            "questionnaire_idem_q", "extra", "TEXT", bind_key="pii"
        ) is True
        assert check_and_add_column(
            "questionnaire_idem_q", "extra", "TEXT", bind_key="pii"
        ) is False

    def test_default_bind_still_works(self, bofs_app_with_binds):
        # Sanity: passing no bind_key targets the default engine, just like
        # all today's existing call sites.
        added = check_and_add_column(
            "participant", "extra_default", "TEXT"
        )
        assert added is True
        cols = {
            c["name"] for c in sa_inspect(bofs_app_with_binds.db.engine).get_columns(
                "participant"
            )
        }
        assert "extra_default" in cols


class TestMakeColumnsNullablePerBind:
    def test_flips_not_null_on_named_bind(self, bofs_app_with_binds):
        engine = bofs_app_with_binds.db.engines["pii"]
        with engine.begin() as conn:
            conn.execute(text(
                'CREATE TABLE nullable_test ('
                '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
                '  required_col TEXT NOT NULL'
                ')'
            ))

        ok = make_columns_nullable(
            "nullable_test", ["required_col"], bind_key="pii"
        )
        assert ok is True

        cols = {
            c["name"]: c
            for c in sa_inspect(engine).get_columns("nullable_test")
        }
        assert cols["required_col"]["nullable"] is True
