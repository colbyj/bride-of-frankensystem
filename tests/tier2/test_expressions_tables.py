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
            "key": None,
            "source": "tables.menu_trials.learning_correct",
        }

    def test_parse_page_predicate_recognises_dotted_int_key(self):
        from BOFS.expressions import parse_page_predicate

        ast, refs = parse_page_predicate(
            "tables.phases.round_score.1 > 0"
        )
        spec = next(iter(refs.values()))
        assert spec["key"] == 1  # digit-only segment coerced to int

    def test_parse_page_predicate_recognises_dotted_str_key(self):
        from BOFS.expressions import parse_page_predicate

        ast, refs = parse_page_predicate(
            "tables.phases.phase_score.learning > 0"
        )
        spec = next(iter(refs.values()))
        assert spec["key"] == "learning"

    def test_parse_page_predicate_rejects_five_part_table_ref(self):
        from BOFS.expressions import parse_page_predicate, ExpressionError

        with pytest.raises(ExpressionError):
            parse_page_predicate("tables.foo.bar.baz.qux > 0")

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


_PHASES_TABLE = {
    "columns": {"phase": {"default": "x"},
                "score": {"type": "integer", "default": 0}},
    "exports": [
        {"group_by": "phase",
         "fields": {"phase_score": "sum(score)"}},
    ],
}


class TestTableRefSubscript:
    """Resolution of subscripted ``tables.X.Y`` refs against group_by exports."""

    def _eval(self, app, pid, predicate):
        from BOFS.expressions import (
            build_participant_env,
            evaluate,
            parse_page_predicate,
            referenced_fields,
        )
        ast, refs = parse_page_predicate(predicate)
        env = build_participant_env(
            pid, referenced_fields(ast), refs,
            app.questionnaires, app.db, tables=app.tables,
        )
        return ast, env, evaluate(ast, env)

    def _seed_phases(self, app):
        table = write_table_file(app, "phases", _PHASES_TABLE)
        pid = _create_participant(app, condition=2)
        _seed_trial(app, table, pid, phase="learning", score=3)
        _seed_trial(app, table, pid, phase="learning", score=4)
        _seed_trial(app, table, pid, phase="recall", score=5)
        return pid

    def test_dotted_str_key_resolves(self, bofs_app):
        pid = self._seed_phases(bofs_app)
        _, _, value = self._eval(
            bofs_app, pid, "tables.phases.phase_score.learning"
        )
        assert value == 7

    def test_bracket_str_key_resolves(self, bofs_app):
        pid = self._seed_phases(bofs_app)
        _, _, value = self._eval(
            bofs_app, pid, 'tables.phases.phase_score["recall"]'
        )
        assert value == 5

    def test_bracket_int_key_resolves(self, bofs_app):
        # Use an int-keyed group_by for this case.
        table = write_table_file(bofs_app, "rounds", {
            "columns": {"round": {"type": "integer", "default": 0},
                        "score": {"type": "integer", "default": 0}},
            "exports": [
                {"group_by": "round",
                 "fields": {"round_score": "max(score)"}},
            ],
        })
        pid = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, pid, round=1, score=10)
        _seed_trial(bofs_app, table, pid, round=2, score=20)

        _, _, value = self._eval(
            bofs_app, pid, "tables.rounds.round_score[2]"
        )
        assert value == 20

    def test_bracket_var_key_resolves(self, bofs_app):
        # ``condition`` is a reserved bare ref; participant.condition is 2.
        # Build a phases table whose keys are 1, 2, 3 so the dict lookup
        # via [condition] hits.
        table = write_table_file(bofs_app, "by_cond", {
            "columns": {"cond": {"type": "integer", "default": 0},
                        "score": {"type": "integer", "default": 0}},
            "exports": [
                {"group_by": "cond",
                 "fields": {"cond_score": "max(score)"}},
            ],
        })
        pid = _create_participant(bofs_app, condition=2)
        _seed_trial(bofs_app, table, pid, cond=1, score=11)
        _seed_trial(bofs_app, table, pid, cond=2, score=22)
        _seed_trial(bofs_app, table, pid, cond=3, score=33)

        _, _, value = self._eval(
            bofs_app, pid, "tables.by_cond.cond_score[condition]"
        )
        assert value == 22

    def test_missing_key_leaves_placeholder_unset(self, bofs_app):
        # Dotted form uses _UNRESOLVED on miss — placeholder absent in env.
        from BOFS.expressions import (
            build_participant_env,
            parse_page_predicate,
            referenced_fields,
        )
        pid = self._seed_phases(bofs_app)
        ast, refs = parse_page_predicate(
            "tables.phases.phase_score.does_not_exist > 0"
        )
        env = build_participant_env(
            pid, referenced_fields(ast), refs,
            bofs_app.questionnaires, bofs_app.db, tables=bofs_app.tables,
        )
        ph = next(iter(refs))
        assert ph not in env

    def test_bare_unkeyed_group_by_ref_returns_dict(self, bofs_app):
        # Without a key, the table ref resolves to the whole dict so an
        # outer subscript node (or e.g. ``len(...)``) can consume it.
        from BOFS.expressions import (
            build_participant_env,
            parse_page_predicate,
            referenced_fields,
        )
        pid = self._seed_phases(bofs_app)
        ast, refs = parse_page_predicate("tables.phases.phase_score")
        env = build_participant_env(
            pid, referenced_fields(ast), refs,
            bofs_app.questionnaires, bofs_app.db, tables=bofs_app.tables,
        )
        ph = next(iter(refs))
        assert isinstance(env.get(ph), dict)
        assert env[ph] == {"learning": 7, "recall": 5}


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

    def test_validate_warns_on_unkeyed_group_by_ref(self, bofs_app):
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

    @pytest.mark.parametrize("predicate", [
        # Dotted int key
        "tables.phases.phase_score.1 > 0",
        # Dotted string key
        "tables.phases.phase_score.learning > 0",
        # Bracket int literal
        "tables.phases.phase_score[1] > 0",
        # Bracket string literal
        'tables.phases.phase_score["learning"] > 0',
        # Bracket variable key (uses ``condition`` from the participant row)
        "tables.phases.phase_score[condition] > 0",
    ])
    def test_validate_does_not_warn_on_keyed_group_by_ref(
        self, bofs_app, predicate
    ):
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
            {"name": "X", "path": "x", "show_if": predicate},
        ])
        results = validate_page_show_if_table_refs(pl.page_list, bofs_app.tables)
        assert not any(
            "group_by" in r.message for r in results
        ), f"Unexpected group_by warning for {predicate!r}: {results}"

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
