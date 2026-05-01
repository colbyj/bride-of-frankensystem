"""
Inline ``{{ expression }}`` substitution for questionnaire JSON.

At render time, every user-facing string in a questionnaire's loaded JSON is
walked. ``{{ ... }}`` placeholders are evaluated as BOFS expressions (the
same DSL used by ``show_if`` and ``participant_calculations``) against the
current participant's stored data and substituted in place. The substituted
value is HTML-escaped so a free-text answer or any other dynamic value
cannot inject markup into the rendered page (questionnaire fields are
otherwise rendered with ``| safe``).

Substitution is single-pass: the result of one substitution is not
re-scanned. This keeps a substituted value of literal ``{{ x }}`` from
triggering a second eval, and sidesteps nested-placeholder ambiguity.

Keys whose values are NOT user-facing copy — expression strings,
compiled ASTs, IDs, question types, asset URLs, or the ``code`` JS slot
where literal ``{{`` is common in third-party templating — are skipped.
"""

import copy
import re

from markupsafe import escape


_PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")


# Keys whose string values are skipped by ``substitute_in_questionnaire``.
# Anything not on this list participates in substitution if it is a string.
_SKIP_KEYS = frozenset({
    "id",
    "questiontype",
    "show_if",
    "participant_calculations",
    "_show_if_ast",
    "_show_if_refs",
    "code",
    "src",
})


def substitute_string(text, participant):
    """Replace every ``{{ expression }}`` in ``text`` with the result of
    evaluating ``expression`` against ``participant`` (using
    :meth:`Participant.evaluate`). Each substituted value is
    HTML-escaped. ``None`` results (parse error, undecided, missing
    data) become an empty string. Non-string ``text`` is returned
    unchanged.
    """
    if not isinstance(text, str) or "{{" not in text:
        return text

    def replace(match):
        expr = match.group(1).strip()
        if not expr:
            return ""
        if participant is None:
            return ""
        value = participant.evaluate(expr)
        if value is None:
            return ""
        return str(escape(str(value)))

    return _PLACEHOLDER_RE.sub(replace, text)


def substitute_in_questionnaire(json_data, participant):
    """Return a deep-copied questionnaire dict with every ``{{ ... }}``
    placeholder substituted, walking nested dicts and lists.

    The original ``json_data`` is the cached
    :class:`JSONQuestionnaire.json_data` and must not be mutated.
    """
    if not isinstance(json_data, dict):
        return json_data
    return _walk_dict(copy.deepcopy(json_data), participant)


def _walk_dict(node, participant):
    for key, value in list(node.items()):
        if key in _SKIP_KEYS:
            continue
        node[key] = _walk_value(value, participant)
    return node


def _walk_value(value, participant):
    if isinstance(value, str):
        return substitute_string(value, participant)
    if isinstance(value, dict):
        return _walk_dict(value, participant)
    if isinstance(value, list):
        return [_walk_value(item, participant) for item in value]
    return value
