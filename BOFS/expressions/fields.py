"""
Helper for parsing expressions whose variable references are BOFS field IDs.

BOFS allows field IDs that are not valid Python identifiers (e.g. ``01_inv``,
which historically appears in deployed questionnaires). The expression parser
itself reuses Python's ``ast`` module and therefore can't see such names as
identifiers. To keep the parser pure, this module pre-substitutes known field
IDs with safe placeholders, parses, and then renames the placeholders back to
the original IDs in the resulting AST.
"""

import re

from .parser import parse


_PY_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_with_field_ids(src, field_ids):
    """
    Parse ``src`` as a BOFS expression where ``field_ids`` may include names
    that are not valid Python identifiers.

    The substitution is token-aware (it won't replace inside larger words),
    sorts longest-first to avoid prefix collisions, and preserves the
    original IDs as ``var`` names in the returned AST.
    """
    if not isinstance(src, str):
        from .parser import ExpressionError
        raise ExpressionError(
            f"expected string expression, got {type(src).__name__}"
        )

    # Sort longest-first so that field IDs sharing a prefix (e.g. ``q1`` and
    # ``q1_followup``) get matched in the right order even if our negative
    # lookbehind/lookahead failed to disambiguate.
    sorted_ids = sorted(set(field_ids), key=len, reverse=True)

    placeholders = {}
    rewritten = src
    for i, fid in enumerate(sorted_ids):
        # Already a valid Python identifier — let ast.parse handle it directly.
        if _PY_IDENT_RE.match(fid):
            continue
        placeholder = f"_bofs_pid_{i}"
        # Match the field id as a standalone token. We can't use \b because
        # field IDs may start with a digit (e.g. ``01_inv``) and \b's notion
        # of word boundaries would mis-fire there. Instead, require that the
        # surrounding characters aren't ASCII word characters.
        pattern = (
            r"(?<![A-Za-z0-9_])" + re.escape(fid) + r"(?![A-Za-z0-9_])"
        )
        rewritten = re.sub(pattern, placeholder, rewritten)
        placeholders[placeholder] = fid

    ast_node = parse(rewritten)
    if placeholders:
        _rename_vars(ast_node, placeholders)
    return ast_node


def _rename_vars(node, mapping):
    if isinstance(node, dict):
        if "var" in node and node["var"] in mapping:
            node["var"] = mapping[node["var"]]
            return
        for value in node.values():
            _rename_vars(value, mapping)
    elif isinstance(node, list):
        for item in node:
            _rename_vars(item, mapping)
