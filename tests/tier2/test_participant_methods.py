"""Tier 2 tests for ``Participant.evaluate``, ``has_questionnaire``,
and the ``TableAccessor`` returned by ``Participant.table``.

These cover the API researchers use to access a participant's stored
data from custom blueprint code and from Jinja templates.
"""

import pytest

from tests.conftest import write_questionnaire_file, write_table_file


SURVEY = {
    "title": "Survey",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "color"},
        {"questiontype": "num_field", "id": "age"},
    ],
}


TRIALS_TABLE = {
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


GROUP_BY_TABLE = {
    "columns": {
        "phase": {"default": "x"},
        "score": {"type": "integer", "default": 0},
    },
    "exports": [
        {
            "group_by": "phase",
            "fields": {
                "phase_score": "sum(score)",
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
    return p


def _seed_survey(app, q, participant_id, **fields):
    row = q.db_class()
    row.participantID = participant_id
    row.tag = ""
    for k, v in fields.items():
        setattr(row, k, v)
    app.db.session.add(row)
    app.db.session.commit()


def _seed_trial(app, table, participant_id, **fields):
    row = table.db_class()
    row.participantID = participant_id
    for k, v in fields.items():
        setattr(row, k, v)
    app.db.session.add(row)
    app.db.session.commit()


# ---------------------------------------------------------------------------
# Participant.evaluate
# ---------------------------------------------------------------------------


class TestParticipantEvaluate:
    def test_constant_expression(self, bofs_app):
        p = _create_participant(bofs_app)
        assert p.evaluate("1 + 1") == 2
        assert p.evaluate("'hello'") == "hello"

    def test_resolves_condition(self, bofs_app):
        p = _create_participant(bofs_app, condition=2)
        assert p.evaluate("condition") == 2
        assert p.evaluate("condition == 2") is True
        assert p.evaluate("condition == 1") is False

    def test_resolves_questionnaire_field(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        _seed_survey(bofs_app, q, p.participantID, color="blue", age=25)

        assert p.evaluate("survey.color == 'blue'") is True
        assert p.evaluate("survey.age >= 18") is True
        assert p.evaluate("survey.age >= 65") is False

    def test_resolves_table_aggregate(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=2, correct=True)

        assert p.evaluate("tables.trials.learning_correct") == 2
        assert p.evaluate("tables.trials.learning_correct >= 2") is True

    def test_returns_none_on_undecided_predicate(self, bofs_app):
        write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        # No submission yet — referencing the field falls into the
        # "undecided" path and the evaluator's caller gets None.
        assert p.evaluate("survey.color == 'blue'") is None

    def test_returns_none_on_unparseable_expression(self, bofs_app):
        p = _create_participant(bofs_app)
        assert p.evaluate("age <") is None

    def test_returns_none_on_non_string_expression(self, bofs_app):
        p = _create_participant(bofs_app)
        assert p.evaluate(None) is None
        assert p.evaluate(42) is None
        assert p.evaluate(["age", ">", "18"]) is None

    def test_compiled_expressions_are_cached(self, bofs_app):
        from BOFS.default.models import _compile_expression
        p = _create_participant(bofs_app)
        _compile_expression.cache_clear()

        p.evaluate("1 + 1")
        p.evaluate("1 + 1")  # cache hit
        info = _compile_expression.cache_info()
        assert info.hits >= 1


# ---------------------------------------------------------------------------
# Participant.has_questionnaire
# ---------------------------------------------------------------------------


class TestHasQuestionnaire:
    def test_returns_false_when_no_submission(self, bofs_app):
        write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        assert p.has_questionnaire("survey") is False

    def test_returns_true_after_submission(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        _seed_survey(bofs_app, q, p.participantID, color="red", age=30)
        assert p.has_questionnaire("survey") is True

    def test_distinguishes_blank_default_from_submission(self, bofs_app):
        """``Participant.questionnaire`` returns a blank-default row when
        nothing has been submitted, so reading ``.color`` on it
        succeeds. ``has_questionnaire`` is what tells you whether the
        row is a real submission."""
        write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        # Blank row exists, but no real submission.
        assert p.questionnaire("survey").color == ""  # default
        assert p.has_questionnaire("survey") is False

    def test_tag_specific(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        _seed_survey(bofs_app, q, p.participantID, color="red", age=30)
        # Tagged search misses the untagged row.
        assert p.has_questionnaire("survey", tag="before") is False

    def test_unknown_questionnaire_returns_false(self, bofs_app):
        p = _create_participant(bofs_app)
        assert p.has_questionnaire("does_not_exist") is False


# ---------------------------------------------------------------------------
# TableAccessor (Participant.table)
# ---------------------------------------------------------------------------


class TestTableAccessor:
    def test_unknown_table_raises_keyerror(self, bofs_app):
        p = _create_participant(bofs_app)
        with pytest.raises(KeyError, match="No table named 'nope'"):
            p.table("nope")

    def test_rows_returns_participants_rows(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=2, correct=False)

        accessor = p.table("trials")
        assert len(accessor.rows) == 2
        assert accessor.rows[0].trial_index == 1
        assert accessor.rows[1].correct is False

    def test_iteration_proxies_to_rows(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=2, correct=True)

        accessor = p.table("trials")
        indices = [row.trial_index for row in accessor]
        assert indices == [1, 2]

    def test_len_proxies_to_rows(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1)
        accessor = p.table("trials")
        assert len(accessor) == 1

    def test_getitem_proxies_to_rows(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=42)
        accessor = p.table("trials")
        assert accessor[0].trial_index == 42

    def test_bool_reflects_row_presence(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        accessor = p.table("trials")
        assert bool(accessor) is False
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1)
        assert bool(p.table("trials")) is True

    def test_export_attribute_runs_aggregate(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=2, correct=False)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=3, correct=True)

        accessor = p.table("trials")
        assert accessor.learning_trials == 3
        assert accessor.learning_correct == 2

    def test_export_filter_is_applied(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="recall", trial_index=2, correct=True)

        accessor = p.table("trials")
        assert accessor.learning_trials == 1
        assert accessor.recall_trials == 1

    def test_export_with_no_rows_returns_none(self, bofs_app):
        write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        accessor = p.table("trials")
        assert accessor.learning_trials is None

    def test_unknown_export_raises_attributeerror(self, bofs_app):
        write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        accessor = p.table("trials")
        with pytest.raises(AttributeError, match="bogus"):
            accessor.bogus

    def test_group_by_export_raises_attributeerror(self, bofs_app):
        write_table_file(bofs_app, "phases", GROUP_BY_TABLE)
        p = _create_participant(bofs_app)
        accessor = p.table("phases")
        with pytest.raises(AttributeError, match="group_by"):
            accessor.phase_score

    def test_export_value_is_memoized(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)

        accessor = p.table("trials")
        first = accessor.learning_correct
        # Second access should be a dict lookup, not another query.
        # We can't directly assert the absence of a query, but we can
        # confirm the value lives in __dict__ after the first access.
        assert "learning_correct" in accessor.__dict__
        assert accessor.learning_correct == first

    def test_exports_property_returns_dict(self, bofs_app):
        table = write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="learning", trial_index=1, correct=True)
        _seed_trial(bofs_app, table, p.participantID,
                    phase="recall", trial_index=2, correct=False)

        accessor = p.table("trials")
        exports = accessor.exports
        assert exports["learning_trials"] == 1
        assert exports["recall_trials"] == 1
        # group_by exports omitted from .exports — there are none in this
        # table, but the dict should not include any unexpected keys.
        assert set(exports) == {
            "learning_trials", "learning_correct", "recall_trials"
        }

    def test_exports_dict_excludes_group_by(self, bofs_app):
        write_table_file(bofs_app, "phases", GROUP_BY_TABLE)
        p = _create_participant(bofs_app)
        accessor = p.table("phases")
        assert accessor.exports == {}

    def test_dunder_lookup_does_not_trigger_query(self, bofs_app):
        write_table_file(bofs_app, "trials", TRIALS_TABLE)
        p = _create_participant(bofs_app)
        accessor = p.table("trials")
        # ``hasattr`` probes for dunder names; ensure none of those raise.
        assert hasattr(accessor, "__class__")
        assert hasattr(accessor, "__iter__")
        assert not hasattr(accessor, "__nonexistent__")
