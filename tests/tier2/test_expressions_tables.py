"""Tier 2 tests for ``tables.<name>.<column>`` expression references.

These tests stand up a real BOFS app with an in-memory SQLite DB, write a
JSONTable with an ``exports`` block, seed rows, and exercise the
expression engine through ``parse_page_predicate`` + ``build_env``.
"""

import pytest

from tests.conftest import write_table_file


TRIALS_TABLE_WITH_EXPORTS = {
    "columns": {
        "phase": {"default": "learning"},
        "trial_index": {"type": "integer", "default": 0},
        "correct": {"type": "boolean", "default": False},
        "response_time_ms": {"type": "integer", "default": 0},
    },
    "exports": [
        {
            "filter": "phase = 'learning'",
            "fields": {
                "learning_trials": "count(trial_index)",
                "learning_correct": "sum(correct)",
            },
        },
        {
            "filter": "phase = 'recall'",
            "fields": {
                "recall_trials": "count(trial_index)",
            },
        },
    ],
}


def _create_participant(app, condition=1):
    p = app.db.Participant()
    p.mTurkID = ""
    p.ipAddress = ""
    p.userAgent = ""
    p.condition = condition
    p.finished = False
    app.db.session.add(p)
    app.db.session.commit()
    return p.participantID


def _seed_trial(app, table, participant_id, **kwargs):
    row = table.db_class()
    row.participantID = participant_id
    for k, v in kwargs.items():
        setattr(row, k, v)
    app.db.session.add(row)
    app.db.session.commit()


class TestTableExpressionRefs:
    def test_parse_page_predicate_recognises_table_ref(self):
        from BOFS.expressions import parse_page_predicate

        ast, refs = parse_page_predicate(
            "tables.menu_trials.learning_correct >= 5"
        )
        assert len(refs) == 1
        spec = next(iter(refs.values()))
        assert spec == {
            "kind": "table",
            "tname": "menu_trials",
            "column": "learning_correct",
            "source": "tables.menu_trials.learning_correct",
        }

    def test_parse_page_predicate_rejects_four_part_table_ref(self):
        from BOFS.expressions import parse_page_predicate, ExpressionError

        with pytest.raises(ExpressionError):
            parse_page_predicate("tables.foo.bar.baz > 0")

    def test_table_ref_resolves_aggregate_value(self, bofs_app):
        from BOFS.expressions import (
            build_participant_env,
            evaluate,
            parse_page_predicate,
            referenced_fields,
        )

        table = write_table_file(
            bofs_app, "menu_trials", TRIALS_TABLE_WITH_EXPORTS
        )
        pid = _create_participant(bofs_app)

        # 3 learning trials, 2 correct
        _seed_trial(bofs_app, table, pid, phase="learning",
                    trial_index=1, correct=True)
        _seed_trial(bofs_app, table, pid, phase="learning",
                    trial_index=2, correct=False)
        _seed_trial(bofs_app, table, pid, phase="learning",
                    trial_index=3, correct=True)

        ast, refs = parse_page_predicate(
            "tables.menu_trials.learning_correct"
        )
        env = build_participant_env(
            pid,
            referenced_fields(ast),
            refs,
            bofs_app.questionnaires,
            bofs_app.db,
            tables=bofs_app.tables,
        )
        value = evaluate(ast, env)
        assert value == 2

    def test_table_ref_predicate_in_show_if(self, bofs_app):
        from BOFS.expressions import (
            build_participant_env,
            evaluate,
            parse_page_predicate,
            referenced_fields,
        )

        table = write_table_file(
            bofs_app, "menu_trials", TRIALS_TABLE_WITH_EXPORTS
        )
        pid = _create_participant(bofs_app)

        _seed_trial(bofs_app, table, pid, phase="learning",
                    trial_index=1, correct=True)
        _seed_trial(bofs_app, table, pid, phase="learning",
                    trial_index=2, correct=True)

        ast, refs = parse_page_predicate(
            "tables.menu_trials.learning_correct >= 2"
        )
        env = build_participant_env(
            pid,
            referenced_fields(ast),
            refs,
            bofs_app.questionnaires,
            bofs_app.db,
            tables=bofs_app.tables,
        )
        assert evaluate(ast, env) is True

    def test_table_ref_with_no_data_is_unresolved(self, bofs_app):
        from BOFS.expressions import (
            build_participant_env,
            parse_page_predicate,
            referenced_fields,
        )

        write_table_file(bofs_app, "menu_trials", TRIALS_TABLE_WITH_EXPORTS)
        pid = _create_participant(bofs_app)

        ast, refs = parse_page_predicate(
            "tables.menu_trials.learning_correct"
        )
        env = build_participant_env(
            pid,
            referenced_fields(ast),
            refs,
            bofs_app.questionnaires,
            bofs_app.db,
            tables=bofs_app.tables,
        )
        # No rows for this participant; the placeholder is left absent so
        # the page-show_if caller treats the predicate as undecided.
        ph = next(iter(refs))
        assert ph not in env

    def test_unknown_table_leaves_placeholder_unset(self, bofs_app):
        from BOFS.expressions import (
            build_participant_env,
            parse_page_predicate,
            referenced_fields,
        )

        pid = _create_participant(bofs_app)

        ast, refs = parse_page_predicate(
            "tables.does_not_exist.score > 0"
        )
        env = build_participant_env(
            pid,
            referenced_fields(ast),
            refs,
            bofs_app.questionnaires,
            bofs_app.db,
            tables=bofs_app.tables,
        )
        # Unknown table → unresolved → placeholder absent from env. The
        # evaluator will then raise ExpressionError, which the page-show_if
        # caller catches and treats as "undecided".
        ph = next(iter(refs))
        assert ph not in env

    def test_unknown_column_leaves_placeholder_unset(self, bofs_app):
        from BOFS.expressions import (
            build_participant_env,
            parse_page_predicate,
            referenced_fields,
        )

        write_table_file(bofs_app, "menu_trials", TRIALS_TABLE_WITH_EXPORTS)
        pid = _create_participant(bofs_app)

        ast, refs = parse_page_predicate(
            "tables.menu_trials.no_such_column > 0"
        )
        env = build_participant_env(
            pid,
            referenced_fields(ast),
            refs,
            bofs_app.questionnaires,
            bofs_app.db,
            tables=bofs_app.tables,
        )
        ph = next(iter(refs))
        assert ph not in env


class TestTableRefValidation:
    def test_validate_warns_on_unknown_table(self, bofs_app):
        from BOFS.PageList import PageList
        from BOFS.validation import validate_page_show_if_table_refs

        pl = PageList([
            {"name": "X", "path": "x",
             "show_if": "tables.does_not_exist.score > 0"},
        ])
        results = validate_page_show_if_table_refs(pl.page_list, bofs_app.tables)
        assert any(
            r.severity == "warning"
            and "does_not_exist" in r.message
            for r in results
        )

    def test_validate_warns_on_unknown_column(self, bofs_app):
        from BOFS.PageList import PageList
        from BOFS.validation import validate_page_show_if_table_refs

        write_table_file(bofs_app, "menu_trials", TRIALS_TABLE_WITH_EXPORTS)

        pl = PageList([
            {"name": "X", "path": "x",
             "show_if": "tables.menu_trials.bogus > 0"},
        ])
        results = validate_page_show_if_table_refs(pl.page_list, bofs_app.tables)
        assert any(
            r.severity == "warning"
            and "bogus" in r.message
            for r in results
        )

    def test_validate_passes_known_ref(self, bofs_app):
        from BOFS.PageList import PageList
        from BOFS.validation import validate_page_show_if_table_refs

        write_table_file(bofs_app, "menu_trials", TRIALS_TABLE_WITH_EXPORTS)

        pl = PageList([
            {"name": "X", "path": "x",
             "show_if": "tables.menu_trials.learning_correct > 0"},
        ])
        results = validate_page_show_if_table_refs(pl.page_list, bofs_app.tables)
        assert results == []

    def test_validate_warns_on_group_by_export_ref(self, bofs_app):
        from BOFS.PageList import PageList
        from BOFS.validation import validate_page_show_if_table_refs

        write_table_file(bofs_app, "phases", {
            "columns": {"phase": {"default": "x"},
                        "score": {"type": "integer"}},
            "exports": [
                {"group_by": "phase",
                 "fields": {"phase_score": "sum(score)"}},
            ],
        })

        pl = PageList([
            {"name": "X", "path": "x",
             "show_if": "tables.phases.phase_score > 0"},
        ])
        results = validate_page_show_if_table_refs(pl.page_list, bofs_app.tables)
        assert any(
            r.severity == "warning" and "group_by" in r.message
            for r in results
        )

    def test_validate_walks_into_conditional_routing(self, bofs_app):
        from BOFS.PageList import PageList
        from BOFS.validation import validate_page_show_if_table_refs

        pl = PageList([
            {"conditional_routing": [
                {"condition": 1, "page_list": [
                    {"name": "Inner", "path": "inner",
                     "show_if": "tables.gone.x > 0"},
                ]},
            ]},
        ])
        results = validate_page_show_if_table_refs(pl.page_list, bofs_app.tables)
        assert any("gone" in r.message for r in results)
