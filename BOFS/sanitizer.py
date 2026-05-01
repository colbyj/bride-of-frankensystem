"""HTML sanitisation for researcher-authored questionnaire content.

Researcher JSON questionnaires intentionally contain HTML for formatting
(``<b>``, lists, embedded media). The questionnaire macro renders these
slots with ``|safe`` so that formatting reaches the browser. To stop a
compromised or copy-pasted snippet from also reaching the admin's browser
as ``<script>`` or ``onerror=...``, we run every researcher-authored HTML
field through ``bleach.clean`` at JSON-load time. The sanitised value
replaces the original in-place so renderers and exports see the clean
text.

The ``code`` slot on a questionnaire (``q.code``) is intentionally left
untouched — researchers use it to embed task-specific JavaScript / Unity
loaders. Sanitising it would break the framework's primary extensibility
point.
"""
import re
from typing import Any

import bleach


# Tags whose contents are JavaScript / CSS / embedded markup, never user-
# visible text. ``bleach.clean(strip=True)`` removes the *tag* but keeps the
# inner text, which would leave script source visible as plain text after
# sanitisation. Pre-strip these blocks (tag + contents) so the text never
# survives.
_DANGEROUS_TAG_BLOCK_RE = re.compile(
    r"<(?P<tag>script|style|template|iframe|frame|frameset|object|embed|noscript)\b[^>]*>"
    r".*?"
    r"</(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
# A self-closing or unmatched dangerous tag (e.g. ``<script src=...>``)
# — drop the tag itself even when no closing tag is present.
_DANGEROUS_TAG_OPEN_RE = re.compile(
    r"<(?:script|style|template|iframe|frame|frameset|object|embed|noscript)\b[^>]*/?>",
    re.IGNORECASE,
)


ALLOWED_TAGS: frozenset = frozenset({
    # Inline text
    "a", "abbr", "b", "big", "br", "cite", "code", "em", "i", "kbd", "mark",
    "q", "s", "samp", "small", "span", "strike", "strong", "sub", "sup",
    "time", "tt", "u", "var",
    # Block-level
    "blockquote", "div", "hr", "p", "pre",
    # Headings
    "h1", "h2", "h3", "h4", "h5", "h6",
    # Lists
    "dd", "dl", "dt", "li", "ol", "ul",
    # Tables
    "caption", "col", "colgroup", "table", "tbody", "td", "tfoot", "th",
    "thead", "tr",
    # Media
    "audio", "figcaption", "figure", "img", "picture", "source", "track",
    "video",
})


ALLOWED_ATTRS: dict = {
    "*": ["class", "dir", "id", "lang", "title"],
    "a": ["href", "rel", "target"],
    "audio": ["autoplay", "controls", "loop", "muted", "preload", "src"],
    "col": ["span"],
    "colgroup": ["span"],
    "img": ["alt", "height", "src", "width"],
    "source": ["media", "src", "type"],
    "td": ["colspan", "headers", "rowspan"],
    "th": ["colspan", "headers", "rowspan", "scope"],
    "track": ["default", "kind", "label", "src", "srclang"],
    "video": ["autoplay", "controls", "height", "loop", "muted", "playsinline",
              "poster", "preload", "src", "width"],
}


# Permitted URL schemes for href/src. ``data:`` is excluded because
# ``data:text/html,<script>...`` is an XSS vector; researchers wanting
# inline images should use ``http(s)://`` or relative paths.
ALLOWED_PROTOCOLS: list = ["http", "https", "mailto"]


def sanitize_html(text: Any) -> Any:
    """Return *text* with disallowed HTML stripped. Non-string values pass
    through unchanged so callers can apply this to mixed-type JSON fields.

    Disallowed tags are removed entirely (``strip=True``) rather than
    escaped — a stray ``<script>`` becomes nothing, not ``&lt;script&gt;``,
    so the visible text isn't disrupted by accidental angle brackets in
    researcher prose. Tags whose contents are script/style/etc. have their
    contents removed too (bleach alone would leave the text behind)."""
    if not isinstance(text, str):
        return text
    text = _DANGEROUS_TAG_BLOCK_RE.sub("", text)
    text = _DANGEROUS_TAG_OPEN_RE.sub("", text)
    return bleach.clean(
        text,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


# Keys whose values should be sanitised everywhere they appear in
# questionnaire JSON. ``code`` is deliberately absent — see module docstring.
_HTML_KEYS_TOP: frozenset = frozenset({"instructions"})
_HTML_KEYS_QUESTION: frozenset = frozenset({
    "instructions",
    "left",
    "prompt",
    "right",
    "text",
    "title",
})


def _sanitize_question(question: dict) -> None:
    """Sanitise HTML-bearing fields on a single question dict in-place,
    descending into ``q_text`` / ``questions`` for grid-style sub-questions."""
    for key in _HTML_KEYS_QUESTION:
        if key in question and isinstance(question[key], str):
            question[key] = sanitize_html(question[key])

    for sub_key in ("questions", "q_text"):
        subs = question.get(sub_key)
        if isinstance(subs, list):
            for sub in subs:
                if isinstance(sub, dict):
                    _sanitize_question(sub)


def sanitize_questionnaire_json(json_data: dict) -> dict:
    """Walk *json_data* in-place, sanitising every researcher-authored HTML
    field. Returns the same dict for caller convenience."""
    if not isinstance(json_data, dict):
        return json_data

    for key in _HTML_KEYS_TOP:
        if key in json_data and isinstance(json_data[key], str):
            json_data[key] = sanitize_html(json_data[key])

    questions = json_data.get("questions")
    if isinstance(questions, list):
        for q in questions:
            if isinstance(q, dict):
                _sanitize_question(q)

    return json_data
