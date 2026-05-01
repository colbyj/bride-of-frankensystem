"""
Hydrate a participant's stored questionnaire answers into an env dict for
the expression engine.

Used by page-level ``show_if`` predicates: at navigation time we walk the
``PageList`` and need to evaluate predicates that may reference fields on
any prior questionnaire the participant has submitted, possibly under a
specific ``tag``.

Reference syntax in source expressions:

* ``condition`` (bare, reserved) — the participant's assigned condition
  number from the ``Participant`` row.
* ``field`` (bare) — looked up across all questionnaires; the most
  recent record wins. Useful when field IDs are unique app-wide.
* ``qname.field`` — most recent submission of ``qname`` (any tag).
* ``qname.tag.field`` — the row of ``qname`` with the given ``tag``.
* ``qname..field`` — the row of ``qname`` with the empty (default) tag,
  stated explicitly.

The parser proper doesn't permit attribute access, so each dotted
reference is replaced with a unique placeholder identifier before parsing
and a side table records what each placeholder resolves to. This keeps the
parser's whitelist tight while letting tags / underscored names round-trip
without ambiguity.

Only the questionnaires actually referenced by the predicate are queried,
so a long PAGE_LIST with many show_if entries doesn't fan out to every
table on every page render.
"""

import re

from .parser import parse, ExpressionError


# Match dotted references: an identifier-looking head, then any number of
# ``.segment`` chains where segments may be empty (so ``q..f`` parses), and
# the whole thing must end with a non-empty segment.
#
# The leading ``[A-Za-z_]`` skips numeric literals like ``3.14``. Middle and
# trailing segments allow leading digits to accommodate tags like ``2023a``
# and field IDs like ``01_inv``.
_DOTTED_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*"
    r"(?:\.[A-Za-z0-9_]*)*"
    r"\.[A-Za-z0-9_]+"
)


# Sentinel returned by ``_resolve_table_ref`` when the reference can't be
# answered from current data — distinguishes "no data yet" from a legitimate
# ``None`` aggregate result.
_UNRESOLVED = object()


def _resolve_table_ref(participant_id, tname, column, db, tables):
    """Resolve a single ``tables.<tname>.<column>`` reference for the
    given participant by delegating to the participant's ``TableAccessor``.

    Returns the aggregate value, or ``_UNRESOLVED`` when the table or
    column can't be found, when the export uses ``group_by`` (ambiguous
    per-reference), or when the participant has no matching rows. The
    caller treats ``_UNRESOLVED`` as "undecided predicate" and keeps the
    page visible.
    """
    if tname not in (tables or {}):
        return _UNRESOLVED

    participant_model = getattr(db, "Participant", None)
    if participant_model is None:
        return _UNRESOLVED
    participant = db.session.get(participant_model, participant_id)
    if participant is None:
        return _UNRESOLVED

    try:
        accessor = participant.table(tname)
        value = getattr(accessor, column)
    except (KeyError, AttributeError):
        return _UNRESOLVED

    if value is None:
        # Either the export legitimately returned NULL, or the participant
        # has no rows — both are "undecided" for show_if purposes.
        return _UNRESOLVED
    return value


def parse_page_predicate(src):
    """Parse a page-level ``show_if`` expression.

    :returns: ``(ast, refs)`` where ``ast`` is the JSON AST and ``refs`` is
        a ``{placeholder_name: spec}`` mapping. The spec ``"kind"`` is one
        of ``"questionnaire"`` (with ``qname``, ``tag``, ``field``) or
        ``"table"`` (with ``tname``, ``column``). The evaluator sees each
        dotted reference as a single ``var`` node whose name is the
        placeholder; :func:`build_env` consults ``refs`` to look up the
        corresponding stored value.
    """
    if not isinstance(src, str):
        raise ExpressionError(
            f"expected string expression, got {type(src).__name__}"
        )

    refs = {}
    counter = [0]

    def _replace(match):
        ref_text = match.group(0)
        parts = ref_text.split(".")

        if parts[0] == "tables":
            # ``tables.<name>.<column>`` — per-participant export of a
            # ``JSONTable``. Tables don't have a tag concept today, so
            # any other arity is an error rather than a silent mis-resolve.
            if len(parts) != 3:
                raise ExpressionError(
                    f"table reference '{ref_text}' must have the form "
                    f"'tables.<name>.<column>'."
                )
            _, tname, column = parts
            placeholder = f"_bofs_ref_{counter[0]}"
            counter[0] += 1
            refs[placeholder] = {
                "kind": "table",
                "tname": tname,
                "column": column,
                "source": ref_text,
            }
            return placeholder

        if len(parts) == 2:
            qname, field = parts
            tag = None  # any tag — most recent wins
        elif len(parts) == 3:
            qname, tag, field = parts
            # tag may be "" from ``q..f`` — explicit empty tag.
        else:
            # 4+ segments: leave the source alone so the parser fails
            # with a clear error rather than us silently mis-resolving.
            return ref_text
        placeholder = f"_bofs_ref_{counter[0]}"
        counter[0] += 1
        refs[placeholder] = {
            "kind": "questionnaire",
            "qname": qname,
            "tag": tag,
            "field": field,
            "source": ref_text,
        }
        return placeholder

    rewritten = _DOTTED_RE.sub(_replace, src)
    ast = parse(rewritten)
    return ast, refs


def build_env(participant_id, referenced, refs, questionnaires, db,
              tables=None):
    """Build an env dict for the expression engine, populated only with
    the names that ``referenced`` actually mentions.

    :param participant_id: BOFS participant primary key.
    :param referenced: iterable of names from ``referenced_fields(ast)``.
    :param refs: placeholder map produced by :func:`parse_page_predicate`.
        Names in ``referenced`` that appear here are resolved according
        to their ``kind`` (``"questionnaire"`` or ``"table"``); the rest
        are treated as bare field references.
    :param questionnaires: dict ``{filename: JSONQuestionnaire}``,
        typically ``current_app.questionnaires``.
    :param db: the BOFS db extension (``current_app.db``).
    :param tables: optional dict ``{filename: JSONTable}``, typically
        ``current_app.tables``. Required when the predicate references
        ``tables.<name>.<column>``.
    :returns: ``{name: value}`` populated with the referenced fields. Any
        name that can't be resolved is left absent — the evaluator will
        raise on it, which is the right failure mode for a typo.
    """
    if not referenced:
        return {}

    refs = refs or {}
    tables = tables or {}
    env = {}

    placeholder_names = set(refs.keys())
    referenced_placeholders = set(referenced) & placeholder_names
    referenced_bare = set(referenced) - placeholder_names

    # ``condition`` is a reserved bare name that resolves to the
    # participant's assigned condition number, not a questionnaire field.
    if "condition" in referenced_bare:
        referenced_bare.discard("condition")
        participant_model = getattr(db, "Participant", None)
        if participant_model is not None:
            participant = db.session.get(participant_model, participant_id)
            if participant is not None:
                env["condition"] = participant.condition

    # Resolve qualified references through the placeholder side table.
    for ph in referenced_placeholders:
        spec = refs[ph]
        kind = spec.get("kind", "questionnaire")

        if kind == "table":
            value = _resolve_table_ref(
                participant_id, spec["tname"], spec["column"], db, tables
            )
            if value is not _UNRESOLVED:
                env[ph] = value
            continue

        qname = spec["qname"]
        tag = spec["tag"]
        field = spec["field"]

        q = questionnaires.get(qname)
        if q is None or q.db_class is None:
            continue

        query = db.session.query(q.db_class).filter(
            q.db_class.participantID == participant_id
        )
        if tag is not None:
            query = query.filter(q.db_class.tag == tag)
        record = query.order_by(q.db_class.timeEnded.desc()).first()
        if record is None:
            continue
        env[ph] = getattr(record, field, None)

    # Resolve bare references: search every questionnaire for a field by
    # this name, taking the most recent matching row regardless of tag.
    for bare in referenced_bare:
        for qname, q in questionnaires.items():
            try:
                field_ids = {f.id for f in q.fetch_fields()}
            except Exception:
                continue
            if bare not in field_ids or q.db_class is None:
                continue
            record = (
                db.session.query(q.db_class)
                .filter(q.db_class.participantID == participant_id)
                .order_by(q.db_class.timeEnded.desc())
                .first()
            )
            if record is not None:
                env.setdefault(bare, getattr(record, bare, None))
                break

    return env
