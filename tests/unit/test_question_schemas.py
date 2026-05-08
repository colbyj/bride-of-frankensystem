"""Tests for the per-template schema loader.

These pin three properties of the template/schema layer:

  * Every built-in question template carries a parseable Google-style
    docstring at the top of its leading ``{# ... #}`` comment.
  * Every type's starter template (whether lifted from an ``Example:`` block
    or synthesised from declared defaults + placeholders) round-trips
    through ``BOFS.validation.validate_questionnaire`` with no errors.
  * Every ``question.<attr>`` access in the template body is covered by
    either the type's per-template ``Args:`` or one of the framework's
    common attributes.
"""

import json
import re
from pathlib import Path

import jinja2
import pytest
from jinja2 import nodes

import BOFS
from BOFS.question_schemas import (
    COMMON_ATTRIBUTES,
    clear_cache,
    get_all_schemas,
    get_schema,
    iter_attribute_names,
)
from BOFS.validation import validate_questionnaire


TEMPLATES_DIR = Path(BOFS.__file__).parent / "templates" / "questions"

# Names referenced in templates that are intentionally not part of the
# editor-facing schema:
#   * ``value`` / ``has_value``: prior-value injection at render time.
#   * ``label_html``: rendered server-side from per-option HTML preprocessing.
#   * ``prior_*``: prior-value telemetry for video/audio/image_click.
#   * Underscore-prefixed names: rendering machinery (``_sub_html`` etc.).
_RENDER_ONLY = {"value", "has_value", "label_html"}


def _template_files() -> list[Path]:
    return sorted(TEMPLATES_DIR.glob("*.html"))


def _question_attr_accesses(template_source: str) -> set[str]:
    """Return every ``question.<attr>`` access in the template body."""
    # BOFS enables jinja2.ext.do for {% do shuffle(...) %} in question
    # templates; mirror that here so the AST parses cleanly.
    env = jinja2.Environment(extensions=["jinja2.ext.do"])
    ast = env.parse(template_source)
    out: set[str] = set()
    for node in ast.find_all(nodes.Getattr):
        if isinstance(node.node, nodes.Name) and node.node.name == "question":
            out.add(node.attr)
    # ``question["foo"]`` is parsed as Getitem with a Const arg.
    for node in ast.find_all(nodes.Getitem):
        if (
            isinstance(node.node, nodes.Name)
            and node.node.name == "question"
            and isinstance(node.arg, nodes.Const)
            and isinstance(node.arg.value, str)
        ):
            out.add(node.arg.value)
    return out


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.parametrize("template_path", _template_files(),
                         ids=lambda p: p.stem)
def test_template_has_parseable_schema(template_path: Path):
    type_id = template_path.stem
    schema = get_schema(type_id)
    assert schema is not None, (
        f"{template_path.name}: no leading {{# ... #}} comment block, or "
        f"the comment block is not a parseable docstring."
    )
    # docstring-parser tolerates missing short_description; we accept blank.
    # The attribute list must include the common attributes that apply to
    # every question type.
    common_names = {a.name for a in COMMON_ATTRIBUTES}
    declared = schema.attribute_names()
    # `required` is dropped for textview and group; `id` is part of every
    # type's effective schema. At minimum every type should have `id` and
    # `questiontype` and `instructions`.
    assert {"id", "questiontype", "instructions"} <= declared, (
        f"{type_id}: schema missing one of id/questiontype/instructions"
    )


@pytest.mark.parametrize("template_path", _template_files(),
                         ids=lambda p: p.stem)
def test_starter_template_validates(template_path: Path):
    type_id = template_path.stem
    schema = get_schema(type_id)
    assert schema is not None
    starter = json.loads(schema.starter_template_text)
    questionnaire = {
        "title": "Schema test",
        "instructions": "",
        "questions": [starter],
    }
    errors = [
        e for e in validate_questionnaire(questionnaire, "test")
        if e.severity == "error"
    ]
    assert errors == [], (
        f"{type_id}: starter does not validate: "
        f"{[e.message for e in errors]}"
    )


@pytest.mark.parametrize("template_path", _template_files(),
                         ids=lambda p: p.stem)
def test_template_attrs_are_declared(template_path: Path):
    """Drift check: every question.<attr> the template reads is declared
    somewhere — either in the per-template Args: block or in
    COMMON_ATTRIBUTES."""
    type_id = template_path.stem
    declared = iter_attribute_names(type_id)
    template_attrs = _question_attr_accesses(template_path.read_text(encoding="utf-8"))
    template_attrs -= _RENDER_ONLY
    template_attrs = {a for a in template_attrs
                      if not a.startswith("_") and not a.startswith("prior_")}
    missing = template_attrs - declared
    assert not missing, (
        f"{type_id}: template reads {sorted(missing)} but the schema does "
        f"not declare them. Add them to the docstring's Args: block or "
        f"COMMON_ATTRIBUTES."
    )


def test_get_all_schemas_covers_every_template():
    """get_all_schemas() should return one entry per *.html in the
    templates/questions directory (no template silently dropped)."""
    schemas = get_all_schemas()
    template_ids = {p.stem for p in _template_files() if not p.stem.startswith("_")}
    assert set(schemas.keys()) == template_ids


def test_get_starter_template_text_uses_example_when_present():
    """When a docstring contains an Example: block, the loader returns its
    JSON verbatim (preserving formatting) rather than synthesising one."""
    schema = get_schema("image_click")
    assert schema is not None
    starter = schema.starter_template_text
    # The verbatim example contains specific keys we authored.
    assert '"questiontype": "image_click"' in starter
    assert '"src": "/static/map.png"' in starter
    # And it parses as JSON.
    parsed = json.loads(starter)
    assert parsed["questiontype"] == "image_click"
