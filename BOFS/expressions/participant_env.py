"""
Hydrate a participant's stored questionnaire answers into an env dict for
the expression engine.

Used by page-level ``show_if`` predicates: at navigation time we walk the
``PageList`` and need to evaluate predicates that may reference fields on
any prior questionnaire the participant has submitted, possibly under a
specific ``tag``.

Reference syntax in source expressions:

* ``condition``, ``source``, ``end_reason`` (bare, reserved) — values
  from the ``Participant`` row itself rather than any questionnaire.
  See :data:`RESERVED_PARTICIPANT_BARE_NAMES`.
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


# Bare names in a ``show_if`` predicate that resolve to scalar attributes on
# the ``Participant`` row rather than to a questionnaire field. Add new
# Participant-backed names here when they should be referenceable from
# expressions; ``getattr`` does the rest in :func:`build_env`.
RESERVED_PARTICIPANT_BARE_NAMES = frozenset({"condition", "source", "end_reason"})


def _resolve_table_ref(participant_id, tname, column, db, tables, key=None):
    """Resolve a single ``tables.<tname>.<column>`` reference for the
    given participant by delegating to the participant's ``TableAccessor``.

    When ``key`` is given, applies it as a dict lookup against a
    ``group_by`` export's per-level dict (with an int/str digit-string
    fallback to absorb SQLite type round-trips). When ``key`` is omitted
    and the column is a ``group_by`` export, returns the entire dict so
    the caller (e.g. an ``ast.Subscript`` evaluator branch) can index it.

    Returns ``_UNRESOLVED`` when the table or column can't be found,
    when the participant has no matching rows, when ``key`` is supplied
    against a non-dict scalar, or when the lookup misses. The caller
    treats ``_UNRESOLVED`` as "undecided predicate" and keeps the page
    visible.
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

    if isinstance(value, dict):
        if key is None:
            # group_by export, no dotted key — hand back the whole dict so
            # bracket-form subscripts can index it via the evaluator.
            return value
        if key in value:
            return value[key]
        # SQLite round-trips integer group_by levels as strings in some
        # paths; try the int coercion before giving up.
        if isinstance(key, str) and key.lstrip("-").isdigit():
            int_key = int(key)
            if int_key in value:
                return value[int_key]
        return _UNRESOLVED

    if key is not None:
        # Caller asked for a subscript on a scalar — undecided.
        return _UNRESOLVED

    return value


def parse_page_predicate(src):
    """Parse a page-level ``show_if`` expression.

    :returns: ``(ast, refs)`` where ``ast`` is the JSON AST and ``refs`` is
        a ``{placeholder_name: spec}`` mapping. The spec ``"kind"`` is one
        of ``"questionnaire"`` (with ``qname``, ``tag``, ``field``) or
        ``"table"`` (with ``tname``, ``column``, and optional literal
        ``key`` from a 4-part ``tables.<name>.<col>.<key>`` ref). The
        evaluator sees each dotted reference as a single ``var`` node
        whose name is the placeholder; :func:`build_env` consults
        ``refs`` to look up the corresponding stored value.
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
            # ``JSONTable``. A 4th segment is a literal key into a
            # ``group_by`` export's per-level dict (digit-only segment
            # is coerced to int so ``round_score.1`` matches an int key).
            if len(parts) == 3:
                _, tname, column = parts
                key = None
            elif len(parts) == 4:
                _, tname, column, raw_key = parts
                key = int(raw_key) if raw_key.lstrip("-").isdigit() else raw_key
            else:
                raise ExpressionError(
                    f"table reference '{ref_text}' must have the form "
                    f"'tables.<name>.<column>' or "
                    f"'tables.<name>.<column>.<key>'."
                )
            placeholder = f"_bofs_ref_{counter[0]}"
            counter[0] += 1
            refs[placeholder] = {
                "kind": "table",
                "tname": tname,
                "column": column,
                "key": key,
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

    # Bare names backed by the ``Participant`` row itself (not by a
    # questionnaire field). ``condition`` is the legacy member of this set;
    # ``source`` and ``end_reason`` join it so ``show_if = "source ==
    # 'prolific'"`` and ``show_if = "end_reason == 'screened_out'"`` work
    # without per-name special cases. ``None`` flows through the evaluator's
    # ``==`` / ``!=`` paths cleanly, so a participant with no source or no
    # recorded end reason matches against any string as ``False``.
    reserved_in_use = referenced_bare & RESERVED_PARTICIPANT_BARE_NAMES
    if reserved_in_use:
        referenced_bare -= reserved_in_use
        participant_model = getattr(db, "Participant", None)
        if participant_model is not None:
            participant = db.session.get(participant_model, participant_id)
            if participant is not None:
                for name in reserved_in_use:
                    env[name] = getattr(participant, name, None)

    # Resolve qualified references through the placeholder side table.
    for ph in referenced_placeholders:
        spec = refs[ph]
        kind = spec.get("kind", "questionnaire")

        if kind == "table":
            value = _resolve_table_ref(
                participant_id, spec["tname"], spec["column"], db, tables,
                key=spec.get("key"),
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
