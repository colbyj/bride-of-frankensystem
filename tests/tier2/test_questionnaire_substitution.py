"""Tier 2 tests for ``{{ expression }}`` substitution in questionnaire JSON.

Covers the public surface in ``BOFS.expressions.substitute`` plus its
integration into ``ParticipantQuestionnaireService.render_questionnaire``.
"""

import copy

import pytest

from BOFS.expressions import (
    substitute_in_questionnaire,
    substitute_string,
)
from BOFS.services.participant_questionnaire import ParticipantQuestionnaireService
from tests.conftest import write_questionnaire_file, write_table_file


SURVEY = {
    "title": "Survey",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "color"},
        {"questiontype": "num_field", "id": "age"},
    ],
}


PHASES_TABLE = {
    "columns": {
        "phase": {"default": "x"},
        "score": {"type": "integer", "default": 0},
    },
    "exports": [
        {"group_by": "phase",
         "fields": {"phase_score": "sum(score)"}},
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


def _seed_survey(app, q, pid, **fields):
    row = q.db_class()
    row.participantID = pid
    row.tag = ""
    for k, v in fields.items():
        setattr(row, k, v)
    app.db.session.add(row)
    app.db.session.commit()


def _seed_table_row(app, table, pid, **fields):
    row = table.db_class()
    row.participantID = pid
    for k, v in fields.items():
        setattr(row, k, v)
    app.db.session.add(row)
    app.db.session.commit()


# ---------------------------------------------------------------------------
# substitute_string
# ---------------------------------------------------------------------------


class TestSubstituteString:
    def test_constant_arithmetic(self, bofs_app):
        p = _create_participant(bofs_app)
        assert substitute_string("{{ 1 + 2 }}", p) == "3"

    def test_no_placeholder_passthrough(self, bofs_app):
        p = _create_participant(bofs_app)
        assert substitute_string("plain text", p) == "plain text"

    def test_non_string_passthrough(self, bofs_app):
        p = _create_participant(bofs_app)
        assert substitute_string(42, p) == 42
        assert substitute_string(None, p) is None

    def test_resolves_questionnaire_field(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        _seed_survey(bofs_app, q, p.participantID, color="blue", age=25)

        assert substitute_string("Hi, {{ survey.color }}!", p) == "Hi, blue!"

    def test_html_escapes_substituted_value(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        _seed_survey(bofs_app, q, p.participantID, color="<script>", age=0)

        result = substitute_string("Color: {{ survey.color }}", p)
        assert result == "Color: &lt;script&gt;"

    def test_unresolved_becomes_empty(self, bofs_app):
        write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        # No submission yet, so survey.color is undecided -> None -> "".
        assert substitute_string("got: {{ survey.color }}.", p) == "got: ."

    def test_parse_error_becomes_empty(self, bofs_app):
        p = _create_participant(bofs_app)
        # ``age <`` is a syntax error; Participant.evaluate returns None.
        assert substitute_string("[{{ age < }}]", p) == "[]"

    def test_empty_placeholder_becomes_empty(self, bofs_app):
        p = _create_participant(bofs_app)
        assert substitute_string("a{{}}b{{   }}c", p) == "abc"

    def test_table_dict_subscript(self, bofs_app):
        table = write_table_file(bofs_app, "phases", PHASES_TABLE)
        p = _create_participant(bofs_app)
        _seed_table_row(bofs_app, table, p.participantID, phase="learning", score=3)
        _seed_table_row(bofs_app, table, p.participantID, phase="learning", score=4)

        result = substitute_string(
            "Learning: {{ tables.phases.phase_score['learning'] }}", p
        )
        assert result == "Learning: 7"

    def test_no_re_scan_of_substituted_text(self, bofs_app):
        """A substituted value that itself looks like a placeholder must
        not trigger a second eval pass — single-pass behaviour is part of
        the contract."""
        q = write_questionnaire_file(bofs_app, "survey", SURVEY)
        p = _create_participant(bofs_app)
        _seed_survey(bofs_app, q, p.participantID,
                     color="{{ 9 + 9 }}", age=0)

        # The stored value contains literal Jinja-like syntax — we expect
        # it to be HTML-escaped and pass through unevaluated.
        result = substitute_string("c={{ survey.color }}", p)
        assert "{{" in result
        assert "18" not in result


# ---------------------------------------------------------------------------
# substitute_in_questionnaire — recursive walk and skip rules
# ---------------------------------------------------------------------------


class TestSubstituteInQuestionnaire:
    def test_walks_top_level_string_fields(self, bofs_app):
        p = _create_participant(bofs_app, condition=2)
        json_data = {
            "title": "Round {{ condition }}",
            "instructions": "Welcome, condition {{ condition }}.",
            "questions": [],
        }
        result = substitute_in_questionnaire(json_data, p)
        assert result["title"] == "Round 2"
        assert result["instructions"] == "Welcome, condition 2."

    def test_walks_per_question_string_fields(self, bofs_app):
        p = _create_participant(bofs_app, condition=3)
        json_data = {
            "title": "Q",
            "instructions": "",
            "questions": [
                {
                    "id": "x",
                    "questiontype": "field",
                    "title": "Heading {{ condition }}",
                    "instructions": "Note {{ condition }}",
                    "placeholder": "p{{ condition }}",
                },
            ],
        }
        result = substitute_in_questionnaire(json_data, p)
        q = result["questions"][0]
        assert q["title"] == "Heading 3"
        assert q["instructions"] == "Note 3"
        assert q["placeholder"] == "p3"

    def test_walks_strings_inside_lists(self, bofs_app):
        p = _create_participant(bofs_app, condition=4)
        json_data = {
            "title": "",
            "instructions": "",
            "questions": [
                {
                    "id": "x",
                    "questiontype": "radiolist",
                    "labels": ["a {{ condition }}", "b"],
                },
                {
                    "id": "y",
                    "questiontype": "radiogrid",
                    "q_text": [
                        {"id": "y1", "text": "row {{ condition }}"},
                    ],
                },
            ],
        }
        result = substitute_in_questionnaire(json_data, p)
        assert result["questions"][0]["labels"] == ["a 4", "b"]
        assert result["questions"][1]["q_text"][0]["text"] == "row 4"

    def test_skips_id_questiontype_show_if(self, bofs_app):
        p = _create_participant(bofs_app, condition=2)
        json_data = {
            "title": "",
            "instructions": "",
            "questions": [
                {
                    "id": "{{ condition }}",         # id NEVER substituted
                    "questiontype": "{{ field }}",   # questiontype NEVER substituted
                    "show_if": "condition == 2",     # expression, NEVER substituted
                    "title": "T",
                },
            ],
        }
        result = substitute_in_questionnaire(json_data, p)
        q = result["questions"][0]
        assert q["id"] == "{{ condition }}"
        assert q["questiontype"] == "{{ field }}"
        assert q["show_if"] == "condition == 2"

    def test_skips_code_field(self, bofs_app):
        p = _create_participant(bofs_app, condition=2)
        json_data = {
            "title": "",
            "instructions": "",
            "code": "<script>const x = `{{ literal }}`;</script>",
            "questions": [],
        }
        result = substitute_in_questionnaire(json_data, p)
        assert result["code"] == "<script>const x = `{{ literal }}`;</script>"

    def test_skips_src(self, bofs_app):
        p = _create_participant(bofs_app, condition=2)
        json_data = {
            "title": "",
            "instructions": "",
            "questions": [
                {
                    "id": "v",
                    "questiontype": "video",
                    "src": "/static/{{ condition }}/intro.mp4",
                },
            ],
        }
        result = substitute_in_questionnaire(json_data, p)
        # src must pass through without substitution.
        assert result["questions"][0]["src"] == "/static/{{ condition }}/intro.mp4"

    def test_does_not_mutate_original(self, bofs_app):
        p = _create_participant(bofs_app, condition=2)
        original = {
            "title": "Hello {{ condition }}",
            "instructions": "",
            "questions": [
                {"id": "x", "questiontype": "field",
                 "title": "T {{ condition }}"},
            ],
        }
        snapshot = copy.deepcopy(original)
        result = substitute_in_questionnaire(original, p)
        assert original == snapshot
        assert result["title"] == "Hello 2"

    def test_passes_through_non_dict_input(self, bofs_app):
        p = _create_participant(bofs_app)
        # Defensive: non-dict json_data returns unchanged.
        assert substitute_in_questionnaire(None, p) is None
        assert substitute_in_questionnaire([1, 2], p) == [1, 2]


# ---------------------------------------------------------------------------
# Render-pipeline integration
# ---------------------------------------------------------------------------


SUBSTITUTION_QUESTIONNAIRE = {
    "title": "Substitution Survey",
    "instructions": "Total clicks across rounds: {{ tables.scores.total }}.",
    "questions": [
        {
            "questiontype": "field",
            "id": "thoughts",
            "title": "Reflection",
            "instructions": "You scored {{ tables.scores.total }} total. Round 1: {{ tables.scores.by_round[1] }}.",
        },
    ],
}


SCORES_TABLE = {
    "columns": {
        "round": {"type": "integer", "default": 0},
        "score": {"type": "integer", "default": 0},
    },
    "exports": [
        {"fields": {"total": "sum(score)"}},
        {"group_by": "round",
         "fields": {"by_round": "max(score)"}},
    ],
}


class TestRenderPipelineSubstitution:
    def _setup(self, app, condition=1):
        write_questionnaire_file(app, "survey", SUBSTITUTION_QUESTIONNAIRE)
        table = write_table_file(app, "scores", SCORES_TABLE)
        p = _create_participant(app, condition=condition)
        _seed_table_row(app, table, p.participantID, round=1, score=5)
        _seed_table_row(app, table, p.participantID, round=2, score=8)
        _seed_table_row(app, table, p.participantID, round=3, score=11)
        return p

    def test_render_questionnaire_substitutes(self, bofs_app):
        p = self._setup(bofs_app)
        # Render a questionnaire through the per-participant service —
        # placeholders should be resolved, the original cached JSON intact.
        from flask import session
        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            session['condition'] = p.condition
            session['currentUrl'] = '/questionnaire/survey'
            html = ParticipantQuestionnaireService(p.participantID) \
                .render_questionnaire(bofs_app.questionnaires['survey'])
        assert "Total clicks across rounds: 24" in html
        assert "You scored 24 total" in html
        assert "Round 1: 5" in html
        # No raw placeholder should leak through.
        assert "{{" not in html

    def test_admin_preview_keeps_raw_placeholders(self, bofs_app):
        # The admin preview path calls render_unloaded_questionnaire
        # directly without going through render_questionnaire, so
        # placeholders should pass through unevaluated.
        self._setup(bofs_app)
        from flask import session
        with bofs_app.test_request_context():
            session['participantID'] = 0  # unused
            html = ParticipantQuestionnaireService.render_unloaded_questionnaire(
                SUBSTITUTION_QUESTIONNAIRE, 'questionnaire.html', tag=''
            )
        # Top-level instructions placeholder should survive verbatim.
        assert "{{ tables.scores.total }}" in html

    def test_cached_json_is_not_mutated_by_render(self, bofs_app):
        p = self._setup(bofs_app)
        cached = bofs_app.questionnaires['survey'].json_data
        snapshot = copy.deepcopy(cached)

        from flask import session
        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            session['condition'] = p.condition
            session['currentUrl'] = '/questionnaire/survey'
            ParticipantQuestionnaireService(p.participantID) \
                .render_questionnaire(bofs_app.questionnaires['survey'])

        assert cached == snapshot
