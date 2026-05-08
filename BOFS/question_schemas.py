"""Loader for per-question-type schemas embedded in Jinja templates.

Each ``BOFS/templates/questions/{type}.html`` carries a Google-style docstring
inside its leading ``{# ... #}`` Jinja comment. The docstring is *both* the
human-readable documentation and the machine-parseable schema:

  * The short description is used as the type's caption in editor UIs.
  * ``Args:`` parameters become the type's per-attribute schema.
  * An optional ``Example:`` block carries a JSON snippet used as the
    Add-Question starter template; when absent, a starter is synthesised
    from the param defaults + placeholders for required scalars.

Common attributes (``id``, ``questiontype``, ``instructions``, ``title``,
``show_if``, plus ``required`` for input types) live in :data:`COMMON_ATTRIBUTES`
and are merged into every type's effective schema by the loader, so per-template
docstrings only declare type-specific fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import docstring_parser


_TEMPLATES_DIR = Path(__file__).parent / "templates" / "questions"

# Display-only types do not accept ``required`` because they have nothing to
# submit. Mirrors BOFS.validation.DISPLAY_ONLY_TYPES.
_DISPLAY_ONLY = frozenset({"textview"})


@dataclass
class Attribute:
    name: str
    type: str
    required: bool
    default: object = None
    description: str = ""


@dataclass
class Schema:
    type_id: str
    description: str
    attributes: list[Attribute]
    starter_template_text: str

    def attribute_names(self) -> set[str]:
        return {a.name for a in self.attributes}


# Common attributes available to every (or almost every) question type. The
# loader merges these into each type's effective attribute list before
# returning a Schema.
COMMON_ATTRIBUTES: list[Attribute] = [
    Attribute(
        "id", "str", required=True,
        description="Unique identifier; becomes the database column name.",
    ),
    Attribute(
        "questiontype", "str", required=True,
        description="Discriminator naming this question's type.",
    ),
    Attribute(
        "instructions", "str", required=False, default="",
        description="Bold heading rendered above the question's input.",
    ),
    Attribute(
        "title", "str", required=False, default="",
        description="Optional text rendered above the question, outside its box.",
    ),
    Attribute(
        "show_if", "str", required=False,
        description="Expression predicate; the question is hidden when it "
                    "evaluates falsy.",
    ),
    Attribute(
        "required", "bool", required=False, default=False,
        description="When true, the participant must answer before continuing.",
    ),
]


def _common_attributes_for(type_id: str) -> list[Attribute]:
    """Filter COMMON_ATTRIBUTES for a specific type. Display-only types
    drop ``required``; ``group`` drops ``required`` (groups are containers,
    not inputs)."""
    out = []
    for attr in COMMON_ATTRIBUTES:
        if attr.name == "required" and (
            type_id in _DISPLAY_ONLY or type_id == "group"
        ):
            continue
        out.append(attr)
    return out


# Matches a Jinja comment {# ... #} at the very start of the file (whitespace
# allowed before). Captures the body, dotall to span multiple lines.
_LEADING_JINJA_COMMENT = re.compile(r"\A\s*\{#(.*?)#\}", re.DOTALL)

# Matches a "Defaults to X." (or "Default is X.") sentence anywhere in a
# parameter description — including across newline-wrapped descriptions,
# which docstring-parser's own default-extractor doesn't handle.
_DEFAULTS_RE = re.compile(
    r"\bDefaults?\s+(?:to|is)\s+(.+?)\.\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _extract_docstring(template_source: str) -> Optional[str]:
    """Return the body of the template's leading ``{# ... #}`` comment, or
    ``None`` if the template has no leading comment."""
    m = _LEADING_JINJA_COMMENT.match(template_source)
    if not m:
        return None
    return m.group(1).strip("\n")


def _parse_default_literal(text: str) -> object:
    """Parse a default literal as it appears after ``Defaults to`` in prose.

    Accepts JSON-ish forms: bare numbers (``1``, ``0.98``), booleans
    (``True``/``False``/``true``/``false``), null, quoted strings (single or
    double), and plain bare words (returned as-is). Falls back to returning
    the trimmed string when JSON parsing fails."""
    trimmed = text.strip().rstrip(".").strip()
    # Normalise Pythonic bool/null spellings to JSON.
    canon = {
        "True": "true", "False": "false", "None": "null",
    }.get(trimmed, trimmed)
    # Single-quoted strings: convert to double-quoted for json.loads.
    if (canon.startswith("'") and canon.endswith("'") and len(canon) >= 2):
        canon = '"' + canon[1:-1].replace('"', r'\"') + '"'
    try:
        return json.loads(canon)
    except (json.JSONDecodeError, ValueError):
        return trimmed


def _extract_default_from_description(p: docstring_parser.DocstringParam) -> object:
    """Return the default value for a param, falling back to scanning the
    description for ``Defaults to X.`` when docstring-parser's own extractor
    didn't find one (which it doesn't for newline-wrapped descriptions)."""
    if p.default is not None:
        return _parse_default_literal(p.default)
    if not p.description:
        return None
    m = _DEFAULTS_RE.search(p.description)
    if not m:
        return None
    return _parse_default_literal(m.group(1))


def _placeholder_for_type(type_name: Optional[str]) -> object:
    """Return the empty/zero value for a JSON type name."""
    t = (type_name or "").strip().lower()
    # Strip ", optional" and similar suffixes if present.
    t = t.split(",")[0].strip()
    return {
        "str": "",
        "string": "",
        "int": 0,
        "integer": 0,
        "float": 0.0,
        "number": 0,
        "bool": False,
        "boolean": False,
        "list": [],
        "array": [],
        "dict": {},
        "object": {},
    }.get(t, "")


def _is_optional(p: docstring_parser.DocstringParam) -> bool:
    """docstring-parser populates ``is_optional`` from ``optional`` annotations
    in the type hint; we also treat any param with a discoverable default as
    optional."""
    if p.is_optional:
        return True
    if _extract_default_from_description(p) is not None:
        return True
    return False


def _attributes_from_params(
    params: list[docstring_parser.DocstringParam],
) -> list[Attribute]:
    out = []
    for p in params:
        type_name = (p.type_name or "").split(",")[0].strip() or "str"
        out.append(Attribute(
            name=p.arg_name,
            type=type_name,
            required=not _is_optional(p),
            default=_extract_default_from_description(p),
            description=(p.description or "").strip(),
        ))
    return out


def _starter_from_example(doc: docstring_parser.Docstring) -> Optional[str]:
    """If the docstring has an ``Example:`` block holding valid JSON, return
    it as a verbatim string. Otherwise return None."""
    for ex in doc.examples:
        text = (ex.description or ex.snippet or "").strip()
        if not text:
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError:
            continue
        return text
    return None


def _synthesise_starter(
    type_id: str, attributes: list[Attribute],
) -> str:
    """Build a starter JSON string from inferred defaults + placeholders.

    Common attributes are included as in a real Add-Question template:
    ``questiontype`` is set to the type id, ``id`` to ``new_<type>``,
    ``instructions`` to the empty string. Per-type required scalars get a
    placeholder for their type; per-type optional scalars use their
    discovered default (when one was declared)."""
    out: dict = {
        "questiontype": type_id,
        "id": f"new_{type_id}",
        "instructions": "",
    }
    for attr in attributes:
        if attr.required:
            out[attr.name] = _placeholder_for_type(attr.type)
        elif attr.default is not None:
            out[attr.name] = attr.default
    return json.dumps(out, indent=4)


def _parse_schema(type_id: str, template_source: str) -> Optional[Schema]:
    """Extract and parse the schema from a template's leading docstring.

    Returns None if the template has no leading ``{# ... #}`` comment block.
    """
    body = _extract_docstring(template_source)
    if body is None:
        return None
    doc = docstring_parser.parse(body)

    type_attrs = _attributes_from_params(doc.params)
    common = _common_attributes_for(type_id)
    # Per-type attributes override commons by name (rare but possible).
    type_names = {a.name for a in type_attrs}
    merged = [c for c in common if c.name not in type_names] + type_attrs

    starter = _starter_from_example(doc)
    if starter is None:
        starter = _synthesise_starter(type_id, type_attrs)

    return Schema(
        type_id=type_id,
        description=(doc.short_description or "").strip(),
        attributes=merged,
        starter_template_text=starter,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_cache: dict[str, Schema] = {}


def _discover_template_paths() -> list[Path]:
    return sorted(_TEMPLATES_DIR.glob("*.html"))


def _build_cache() -> dict[str, Schema]:
    out: dict[str, Schema] = {}
    for path in _discover_template_paths():
        type_id = path.stem
        # Ignore partials/macros that aren't a question type. Convention:
        # files starting with ``_`` are partials.
        if type_id.startswith("_"):
            continue
        source = path.read_text(encoding="utf-8")
        schema = _parse_schema(type_id, source)
        if schema is not None:
            out[type_id] = schema
    return out


def clear_cache() -> None:
    """Drop the cached schemas. Call this from tests after writing a
    temporary template."""
    _cache.clear()


def get_all_schemas() -> dict[str, Schema]:
    """Return ``{type_id: Schema}`` for every question type whose template
    carries a parseable schema docstring. Cached after the first call."""
    if not _cache:
        _cache.update(_build_cache())
    return dict(_cache)


def get_schema(type_id: str) -> Optional[Schema]:
    """Return the Schema for ``type_id``, or ``None`` if no template has one."""
    return get_all_schemas().get(type_id)


def get_starter_template_text(type_id: str) -> Optional[str]:
    """Return the starter JSON for a type, or ``None`` if the type isn't
    registered. The starter is verbatim from the template's ``Example:``
    block when present, else synthesised from declared defaults +
    placeholders."""
    schema = get_schema(type_id)
    return None if schema is None else schema.starter_template_text


def iter_attribute_names(type_id: str) -> set[str]:
    """Return the full set of attribute names a type accepts (per-type
    declarations ∪ applicable common attributes)."""
    schema = get_schema(type_id)
    return set() if schema is None else schema.attribute_names()
