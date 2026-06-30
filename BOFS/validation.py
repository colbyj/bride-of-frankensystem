"""
Validation module for BOFS questionnaire JSON files.

Provides pure validation functions that check questionnaire structure,
field IDs, question types, and calculated fields. Used both at startup
(to show helpful error pages) and in the test suite.
"""

import keyword
import re
import os
from difflib import get_close_matches


def _scan_builtin_types() -> frozenset:
    """Discover built-in question types from BOFS/templates/questions/*.html."""
    questions_dir = os.path.join(os.path.dirname(__file__), "templates", "questions")
    if os.path.isdir(questions_dir):
        return frozenset(f[:-5] for f in os.listdir(questions_dir) if f.endswith(".html"))
    return frozenset()


# Valid question types shipped with BOFS, discovered from the templates directory
BUILTIN_QUESTION_TYPES = _scan_builtin_types()

# Question types that don't produce database columns (display-only)
DISPLAY_ONLY_TYPES = frozenset({"textview"})

# Container types whose own ``id`` is structural (HTML wrapper) and never
# produces a DB column — only their nested sub-questions contribute columns.
CONTAINER_TYPES = frozenset({"group"})

# Question types whose top-level `id` expands into multiple suffixed columns.
# Maps questiontype -> list of (suffix, datatype) pairs.
EXPANDED_TYPES = {
    "video": [("_started", "float"), ("_ended", "float"), ("_watched", "float")],
    "audio": [("_started", "float"), ("_ended", "float"), ("_listened", "float")],
}


def discover_question_types(app) -> frozenset:
    """
    Scan all template directories for question type templates.

    Looks in:
    - BOFS/templates/questions/ (built-in types)
    - <project_root>/templates/questions/ (project-level custom types)
    - <blueprint>/templates/questions/ (blueprint-level custom types)

    Returns a frozenset of type names (filename without .html extension).
    """
    types = set()
    dirs_to_scan = []

    # Built-in BOFS templates
    bofs_questions = os.path.join(app.bofs_path, "templates", "questions")
    dirs_to_scan.append(bofs_questions)

    # Project-level templates
    project_questions = os.path.join(app.instance_path, "templates", "questions")
    dirs_to_scan.append(project_questions)

    # Blueprint-level templates
    for blueprint_name, blueprint in app.blueprints.items():
        if blueprint.template_folder:
            bp_questions = os.path.join(blueprint.root_path, blueprint.template_folder, "questions")
            dirs_to_scan.append(bp_questions)

    for d in dirs_to_scan:
        if os.path.isdir(d):
            for filename in os.listdir(d):
                if filename.endswith(".html"):
                    types.add(filename[:-5])  # strip .html

    return frozenset(types)

# Column names reserved by BOFS's create_db_class()
RESERVED_COLUMNS = frozenset({
    "participantID", "participant", "tag",
    "timeStarted", "timeEnded", "duration",
})

# Names reserved at the expression layer. These resolve to participant- or
# app-level state inside ``show_if`` and ``participant_calculations``
# expressions, so a field ID or calc key with the same name would shadow
# the reserved meaning. Kept separate from RESERVED_COLUMNS because the
# error message and rationale differ — these aren't database columns.
RESERVED_EXPRESSION_NAMES = frozenset({
    "condition",
    "tables",
})

# Regex for SQL-safe identifiers: letter or underscore, then alphanumeric/underscore
_SQL_SAFE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Accept hex (#rgb / #rrggbb / #rrggbbaa), CSS named colors, or rgb()/rgba()/hsl()/hsla()
# functional notation. Restricting the character set blocks CSS/HTML injection via
# the inline <style> block in template.html.
_HEADER_COLOR_RE = re.compile(
    r'^\s*('
    r'#[0-9a-fA-F]{3,8}'
    r'|[a-zA-Z]{3,32}'
    r'|(?:rgb|rgba|hsl|hsla)\([0-9eE\s,.%/+\-]+\)'
    r')\s*$'
)

# Identifiers allowed inside JSONTable export expressions ('fields', 'filter',
# 'having'). Researcher-authored expressions are wrapped in
# ``db.literal_column`` / ``db.text`` which interpolate them as raw SQL — the
# allow-list below is the only thing standing between the JSON file and
# arbitrary SQL execution. Lowercase; identifier matching is case-insensitive.
_SQL_EXPR_KEYWORDS = frozenset({
    "and", "or", "not", "is", "null", "in", "between", "like", "ilike",
    "case", "when", "then", "else", "end", "distinct",
    "true", "false",
    "asc", "desc", "as",
})

# Aggregate / scalar functions known to be side-effect-free on SQLite and
# Postgres. Researchers reach for these in practice (``count``, ``avg``, etc.).
# Anything outside this set is rejected, which blocks ``load_extension``,
# ``randomblob``, and other SQLite footguns alongside genuinely dangerous
# functions in other dialects.
_SQL_EXPR_FUNCTIONS = frozenset({
    "count", "sum", "avg", "min", "max", "total",
    "abs", "round", "ceil", "ceiling", "floor",
    "coalesce", "ifnull", "nullif",
    "length", "lower", "upper", "trim", "ltrim", "rtrim",
    "cast",  # cast(x as integer) — note 'as' is in keywords
})

# Identifiers that are never allowed in a researcher-authored expression even
# when the rest of the syntax looks tame. Anything containing these tokens is
# rejected outright.
_SQL_EXPR_FORBIDDEN_KEYWORDS = frozenset({
    "select", "from", "where", "join", "union", "intersect", "except",
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "exec", "execute", "attach", "detach", "pragma", "vacuum", "analyze",
    "grant", "revoke", "replace", "into", "values", "merge",
    "load_extension", "load", "savepoint", "release", "rollback",
    "commit", "begin", "transaction",
})

# Single-char operator/punctuation chars permitted in expressions.
_SQL_EXPR_OPERATOR_CHARS = frozenset("=<>!+-*/(),.")


def is_sql_expression_safe(expr: str) -> tuple:
    """Validate a researcher-authored SQL fragment used in JSONTable export
    ``fields`` values, ``filter``, or ``having`` clauses.

    These fragments are wrapped in ``db.literal_column`` / ``db.text`` and
    interpolated verbatim into SELECT/WHERE/HAVING. The validator enforces
    an allow-list of tokens that covers the patterns researchers actually
    write (``count(trial_index)``, ``avg(case when correct = 1 then 1.0
    else 0.0 end)``, ``phase = 'learning'``) and rejects the SQL-injection
    primitives (``;``, ``--``, ``/* ... */``, quoted identifiers, dangerous
    keywords).

    Returns ``(True, "")`` if safe, ``(False, reason)`` otherwise.
    """
    if not isinstance(expr, str):
        return False, f"expression must be a string, got {type(expr).__name__}"
    if not expr.strip():
        return False, "expression is empty"
    if len(expr) > 1024:
        return False, "expression exceeds 1024 characters"

    i = 0
    n = len(expr)
    found_identifiers: list = []

    while i < n:
        ch = expr[i]

        # Whitespace
        if ch.isspace():
            i += 1
            continue

        # Identifier or keyword (case-insensitive)
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            token = expr[i:j].lower()
            if token in _SQL_EXPR_FORBIDDEN_KEYWORDS:
                return False, f"forbidden keyword: {token!r}"
            found_identifiers.append((token, i))
            i = j
            continue

        # Number (integer or float, including leading dot)
        if ch.isdigit() or (ch == "." and i + 1 < n and expr[i + 1].isdigit()):
            j = i
            saw_dot = False
            while j < n and (expr[j].isdigit() or (expr[j] == "." and not saw_dot)):
                if expr[j] == ".":
                    saw_dot = True
                j += 1
            i = j
            continue

        # Single-quoted string literal. SQL doubles the quote to escape it
        # ('it''s'); we accept that but nothing else (no backslash escapes).
        if ch == "'":
            j = i + 1
            while j < n:
                if expr[j] == "'":
                    if j + 1 < n and expr[j + 1] == "'":
                        j += 2  # escaped quote
                        continue
                    j += 1  # closing quote
                    break
                if expr[j] == "\\":
                    return False, "backslash escapes are not allowed in string literals"
                j += 1
            else:
                return False, "unterminated string literal"
            i = j
            continue

        # Comment start sequences must be checked before the single-char
        # operator branch — both `-` and `/` are otherwise valid operators.
        if i + 1 < n:
            two = expr[i:i + 2]
            if two == "--":
                return False, "SQL line comments (--) are not allowed"
            if two == "/*":
                return False, "SQL block comments (/* */) are not allowed"

        # Two-char operators that need to be recognised before falling back
        # to the single-char check (so we don't accidentally reject `!=` and
        # `<>` by treating `!` or `>` as standalone).
        if i + 1 < n and expr[i:i + 2] in ("!=", "<>", "<=", ">=", "||"):
            i += 2
            continue

        # Single-char operator / punctuation
        if ch in _SQL_EXPR_OPERATOR_CHARS:
            i += 1
            continue

        # Anything else (including `;`, `"`, backtick, `--`, `/*`, `\`) is
        # rejected. Calling out the common SQL-injection primitives gives a
        # better error message than a generic "unexpected character".
        if ch == ";":
            return False, "semicolons are not allowed"
        if ch == "\\":
            return False, "backslashes are not allowed"
        if ch in ('"', "`"):
            return False, "quoted identifiers (\" or `) are not allowed"
        if ch == "-" and i + 1 < n and expr[i + 1] == "-":
            return False, "SQL line comments (--) are not allowed"
        if ch == "/" and i + 1 < n and expr[i + 1] == "*":
            return False, "SQL block comments (/* */) are not allowed"
        return False, f"unexpected character {ch!r} at position {i}"

    # Identifiers used as function calls (next non-space char is '(') must be
    # in the function allow-list. Other identifiers are treated as column
    # names — SQLAlchemy will fail loudly at query time if they're unknown.
    for idx, (tok, pos) in enumerate(found_identifiers):
        if tok in _SQL_EXPR_KEYWORDS:
            continue
        # Look ahead in the original string for an opening paren.
        # The next non-space character determines whether this is a call.
        scan = pos + len(tok)
        while scan < n and expr[scan].isspace():
            scan += 1
        if scan < n and expr[scan] == "(":
            if tok not in _SQL_EXPR_FUNCTIONS:
                return False, (
                    f"function {tok!r} is not in the allow-list. "
                    f"Allowed: {', '.join(sorted(_SQL_EXPR_FUNCTIONS))}"
                )

    return True, ""


class ValidationResult:
    """A single validation finding (error or warning) with context for helpful messages."""

    def __init__(self, severity: str, questionnaire: str, message: str, suggestion: str = None):
        """
        :param severity: 'error' or 'warning'
        :param questionnaire: filename of the questionnaire (or 'PAGE_LIST' for cross-ref checks)
        :param message: what went wrong
        :param suggestion: actionable fix advice (optional)
        """
        self.severity = severity
        self.questionnaire = questionnaire
        self.message = message
        self.suggestion = suggestion

    def __str__(self):
        prefix = {"error": "ERROR", "warning": "WARNING", "info": "NOTE"}.get(
            self.severity, self.severity.upper()
        )
        s = f"  {prefix} in '{self.questionnaire}': {self.message}"
        if self.suggestion:
            s += f"\n    -> {self.suggestion}"
        return s

    def __repr__(self):
        return f"ValidationResult({self.severity!r}, {self.questionnaire!r}, {self.message!r})"


def is_sql_safe(name: str) -> bool:
    """Check if a string is a valid SQL column identifier."""
    return bool(_SQL_SAFE_RE.match(name))


def is_python_attribute_safe(name: str) -> bool:
    """Check if ``name`` is usable as a Python attribute (so
    ``participant.questionnaire('survey').name`` reads the field rather
    than being a SyntaxError). Requires a valid identifier that isn't a
    Python keyword."""
    return bool(_SQL_SAFE_RE.match(name)) and not keyword.iskeyword(name)


def is_valid_header_color(value) -> bool:
    """Check if ``value`` is a CSS color safe to interpolate into the
    inline ``<style>`` block in template.html. Accepts hex (#rgb /
    #rrggbb / #rrggbbaa), CSS named colors, and rgb()/rgba()/hsl()/hsla()
    functional notation. Restricting the character set blocks CSS/HTML
    injection via the HEADER_COLOR config value."""
    return isinstance(value, str) and bool(_HEADER_COLOR_RE.match(value))


def _ids_for_question(q: dict, i: int, ids: list) -> None:
    """Append (field_id, i) pairs for a single question definition.

    Mirrors the column-emission rules in
    ``JSONQuestionnaire._emit_question_columns``:
      * Container questions with non-empty nested ``questions``/``q_text``
        emit row ids only — the parent id is structural.
      * ``EXPANDED_TYPES`` (audio, video) fan out into suffixed ids.
      * ``image_click`` fans out into ``_x``/``_y`` (single-click) or one
        bare id (multi-click).
      * Generic 1:1 case adds the bare id.
    """
    if not isinstance(q, dict):
        return

    nested = q.get("questions") or q.get("q_text")
    if isinstance(nested, list) and len(nested) > 0:
        # Container case — parent id is not a field. Emit row ids only.
        for sub in nested:
            if isinstance(sub, dict) and "id" in sub:
                ids.append((sub["id"], i))
        return

    if "id" not in q:
        return

    qtype = q.get("questiontype")
    fid = q["id"]
    if qtype in EXPANDED_TYPES and isinstance(fid, str):
        for suffix, _dtype in EXPANDED_TYPES[qtype]:
            ids.append((fid + suffix, i))
    elif qtype == "image_click" and isinstance(fid, str):
        max_clicks = q.get("max_clicks", 1)
        if isinstance(max_clicks, int) and max_clicks == 1:
            ids.append((fid + "_x", i))
            ids.append((fid + "_y", i))
        else:
            ids.append((fid, i))
    else:
        ids.append((fid, i))


def _collect_field_ids(json_data: dict) -> list[tuple[str, int]]:
    """
    Walk the questions list and return (field_id, question_index) pairs,
    mirroring the logic in JSONQuestionnaire.fetch_fields().
    """
    ids: list[tuple[str, int]] = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return ids

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        if q.get("questiontype") == "group":
            # Sub-questions of any non-group type (including textview, which
            # has no id) are walked through the standard id collector so
            # column-emitting subs contribute columns and id-less ones don't.
            for sub in q.get("questions", []) or []:
                if isinstance(sub, dict) and sub.get("questiontype") != "group":
                    _ids_for_question(sub, i, ids)
            continue
        _ids_for_question(q, i, ids)

    return ids


# ---------------------------------------------------------------------------
# Individual validation functions
# ---------------------------------------------------------------------------

def validate_structure(json_data: dict, filename: str) -> list[ValidationResult]:
    """Check that the JSON has a 'questions' list."""
    results = []

    if "questions" not in json_data:
        results.append(ValidationResult(
            "error", filename,
            "Missing 'questions' key. Every questionnaire JSON must have a top-level 'questions' array.",
            "Add a \"questions\": [ ... ] array containing your question definitions."
        ))
        return results  # Can't validate further

    if not isinstance(json_data["questions"], list):
        results.append(ValidationResult(
            "error", filename,
            f"'questions' must be a list, but got {type(json_data['questions']).__name__}.",
            "Ensure 'questions' is a JSON array: \"questions\": [ {{ ... }}, {{ ... }} ]"
        ))
        return results

    if len(json_data["questions"]) == 0:
        results.append(ValidationResult(
            "warning", filename,
            "The 'questions' array is empty. This questionnaire has no questions.",
        ))

    return results


def validate_question_types(json_data: dict, filename: str,
                            valid_types: frozenset = None) -> list[ValidationResult]:
    """Check that every question has a recognized questiontype."""
    if valid_types is None:
        valid_types = BUILTIN_QUESTION_TYPES

    results = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return results

    sorted_types = sorted(valid_types)

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} is not a JSON object (got {type(q).__name__}).",
                "Each entry in the 'questions' array must be a JSON object {{ ... }}."
            ))
            continue

        if "questiontype" not in q:
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} is missing 'questiontype'.",
                "Add a \"questiontype\" field. Available types: " + ", ".join(sorted_types)
            ))
            continue

        qtype = q["questiontype"]
        if qtype not in valid_types:
            suggestion = f"Available types: {', '.join(sorted_types)}"
            close = get_close_matches(qtype, sorted_types, n=1, cutoff=0.5)
            if close:
                suggestion = f"Did you mean '{close[0]}'? " + suggestion
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} uses unknown questiontype '{qtype}'.",
                suggestion
            ))
            continue

        # Validate sub-question types inside a group. Nested groups and
        # textview sub-questions are reported separately by
        # validate_question_ids; here we only check that other sub-types
        # are recognised so a typo'd sub-questiontype gets the same
        # "did you mean" treatment.
        if qtype == "group":
            for j, sub in enumerate(q.get("questions", []) or []):
                if not isinstance(sub, dict):
                    continue
                sub_type = sub.get("questiontype")
                if sub_type is None:
                    results.append(ValidationResult(
                        "error", filename,
                        f"Question #{i+1} ('group'), sub-item #{j+1} is "
                        f"missing 'questiontype'.",
                        "Add a \"questiontype\" field on each sub-question."
                    ))
                    continue
                if sub_type == "group":
                    # Nested groups: reported by validate_question_ids with
                    # a clearer message; skip the unknown-type check here.
                    continue
                if sub_type not in valid_types:
                    suggestion = f"Available types: {', '.join(sorted_types)}"
                    close = get_close_matches(sub_type, sorted_types, n=1, cutoff=0.5)
                    if close:
                        suggestion = f"Did you mean '{close[0]}'? " + suggestion
                    results.append(ValidationResult(
                        "error", filename,
                        f"Question #{i+1} ('group'), sub-item #{j+1} uses "
                        f"unknown questiontype '{sub_type}'.",
                        suggestion
                    ))

    return results


def validate_question_ids(json_data: dict, filename: str) -> list[ValidationResult]:
    """
    Check that non-display questions have IDs, and that questions which
    use nested sub-questions (radiogrid, checklist, group) have IDs on
    those sub-items. Also enforces group-specific rules: groups must have
    a non-empty ``questions`` list, and sub-questions of a group cannot
    themselves be ``textview`` or another ``group``.
    """
    results = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return results

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue

        qtype = q.get("questiontype", "")

        # Display-only types don't need IDs
        if qtype in DISPLAY_ONLY_TYPES:
            continue

        if qtype == "group":
            subs = q.get("questions")
            if not isinstance(subs, list) or len(subs) == 0:
                results.append(ValidationResult(
                    "error", filename,
                    f"Question #{i+1} ('group') has no sub-questions.",
                    "Add a non-empty \"questions\" array containing the "
                    "sub-questions to render inside the group."
                ))
                continue
            for j, sub in enumerate(subs):
                if not isinstance(sub, dict):
                    continue
                sub_type = sub.get("questiontype", "")
                if sub_type == "group":
                    results.append(ValidationResult(
                        "error", filename,
                        f"Question #{i+1} ('group'), sub-item #{j+1} is "
                        f"itself a 'group'. Nested groups are not supported.",
                        "Flatten the structure: list all sub-questions "
                        "directly inside the outer group."
                    ))
                    continue
                # Display-only sub-types (textview) intentionally have no id.
                if sub_type in DISPLAY_ONLY_TYPES:
                    continue
                # Sub-questions still need their own IDs (or nested IDs).
                sub_nested = sub.get("questions") or sub.get("q_text")
                if isinstance(sub_nested, list) and len(sub_nested) > 0:
                    for k, row in enumerate(sub_nested):
                        if isinstance(row, dict) and "id" not in row:
                            results.append(ValidationResult(
                                "warning", filename,
                                f"Question #{i+1} ('group'), sub-item #{j+1} "
                                f"('{sub_type}'), row #{k+1} has no 'id'. "
                                f"It will not be stored in the database.",
                                "Add an \"id\" field to each row that "
                                "should be recorded."
                            ))
                elif "id" not in sub:
                    results.append(ValidationResult(
                        "warning", filename,
                        f"Question #{i+1} ('group'), sub-item #{j+1} "
                        f"('{sub_type}') has no 'id'. It will not be "
                        f"stored in the database.",
                        "Add an \"id\" field if this sub-question's "
                        "response should be recorded."
                    ))
            continue

        nested = q.get("questions") or q.get("q_text")
        has_nested = isinstance(nested, list) and len(nested) > 0

        # If there are nested sub-questions, check them for IDs
        if has_nested:
            for j, sub in enumerate(nested):
                if isinstance(sub, dict) and "id" not in sub:
                    results.append(ValidationResult(
                        "warning", filename,
                        f"Question #{i+1} ('{qtype}'), sub-item #{j+1} has no 'id'. "
                        f"It will not be stored in the database.",
                        "Add an \"id\" field to each sub-item that should be recorded."
                    ))
        elif "id" not in q:
            # Top-level non-display question with no nested items and no ID
            results.append(ValidationResult(
                "warning", filename,
                f"Question #{i+1} ('{qtype}') has no 'id'. It will not be stored in the database.",
                "Add an \"id\" field if this question's response should be recorded."
            ))

    return results


def validate_field_ids(json_data: dict, filename: str) -> list[ValidationResult]:
    """Check field ID uniqueness, SQL safety, and reserved name collisions."""
    results = []
    ids = _collect_field_ids(json_data)

    if not ids:
        return results

    # Check SQL safety
    for field_id, q_idx in ids:
        if not isinstance(field_id, str):
            results.append(ValidationResult(
                "error", filename,
                f"Field ID in question #{q_idx+1} is not a string (got {type(field_id).__name__}).",
                "Field IDs must be strings."
            ))
            continue

        if not is_sql_safe(field_id):
            results.append(ValidationResult(
                "error", filename,
                f"Field ID '{field_id}' (question #{q_idx+1}) is not a valid column name.",
                "IDs must start with a letter or underscore, and contain only letters, "
                "numbers, and underscores. No spaces, dashes, or special characters."
            ))
        elif keyword.iskeyword(field_id):
            results.append(ValidationResult(
                "error", filename,
                f"Field ID '{field_id}' (question #{q_idx+1}) is a Python keyword.",
                f"Templates and custom code read field values via attribute "
                f"access (e.g. participant.questionnaire('{filename}')."
                f"{field_id}), which is a syntax error for keywords. "
                f"Choose a different ID."
            ))

    # Check reserved names
    for field_id, q_idx in ids:
        if not isinstance(field_id, str):
            continue
        if field_id in RESERVED_COLUMNS:
            results.append(ValidationResult(
                "error", filename,
                f"Field ID '{field_id}' (question #{q_idx+1}) conflicts with a reserved BOFS column name.",
                f"Reserved names: {', '.join(sorted(RESERVED_COLUMNS))}. Choose a different ID."
            ))
        elif field_id in RESERVED_EXPRESSION_NAMES:
            results.append(ValidationResult(
                "error", filename,
                f"Field ID '{field_id}' (question #{q_idx+1}) conflicts with a reserved expression name.",
                f"'{field_id}' is reserved for use in show_if and "
                f"participant_calculations expressions. Choose a different ID."
            ))

    # Check uniqueness
    seen: dict[str, int] = {}
    for field_id, q_idx in ids:
        if not isinstance(field_id, str):
            continue
        if field_id in seen:
            results.append(ValidationResult(
                "error", filename,
                f"Duplicate field ID '{field_id}' in question #{q_idx+1} "
                f"(first seen in question #{seen[field_id]+1}).",
                "Each field ID must be unique within a questionnaire. Rename one of the duplicates."
            ))
        else:
            seen[field_id] = q_idx

    return results


def validate_image_select(json_data: dict, filename: str) -> list[ValidationResult]:
    """Check that image_select questions have a well-formed `images` list."""
    results = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return results

    for i, q in enumerate(questions):
        if not isinstance(q, dict) or q.get("questiontype") != "image_select":
            continue

        images = q.get("images")
        if images is None:
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} ('image_select') is missing the required 'images' field.",
                'Add an "images" array, e.g. '
                '[{"src": "/static/foo.png", "value": "a", "label": "Option A"}, ...]'
            ))
            continue

        if not isinstance(images, list):
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} ('image_select'): 'images' must be a list, "
                f"got {type(images).__name__}."
            ))
            continue

        if len(images) == 0:
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} ('image_select'): 'images' is empty.",
                "Add at least one image entry."
            ))
            continue

        seen_values: dict = {}
        for j, img in enumerate(images):
            if not isinstance(img, dict):
                results.append(ValidationResult(
                    "error", filename,
                    f"Question #{i+1} ('image_select'), image #{j+1} is not an object "
                    f"(got {type(img).__name__})."
                ))
                continue

            src = img.get("src")
            if not isinstance(src, str) or not src:
                results.append(ValidationResult(
                    "error", filename,
                    f"Question #{i+1} ('image_select'), image #{j+1} is missing a 'src' string.",
                    "Each image needs a 'src' URL (e.g., '/static/foo.png')."
                ))

            if "value" not in img:
                results.append(ValidationResult(
                    "error", filename,
                    f"Question #{i+1} ('image_select'), image #{j+1} is missing a 'value'.",
                    "Each image needs a 'value' that will be stored when this option is selected."
                ))
            else:
                v = img["value"]
                if isinstance(v, (str, int, float, bool)):
                    if v in seen_values:
                        results.append(ValidationResult(
                            "warning", filename,
                            f"Question #{i+1} ('image_select'): image #{j+1} reuses "
                            f"value {v!r} (first seen in image #{seen_values[v]+1}). "
                            f"Submitted responses won't be distinguishable between these options."
                        ))
                    else:
                        seen_values[v] = j

    return results


def validate_image_click(json_data: dict, filename: str) -> list[ValidationResult]:
    """Check that image_click questions have a usable image and a sane max_clicks."""
    results = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return results

    for i, q in enumerate(questions):
        if not isinstance(q, dict) or q.get("questiontype") != "image_click":
            continue

        src = q.get("src")
        if not isinstance(src, str) or not src:
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} ('image_click') is missing the required 'src' string.",
                'Add a "src" pointing at the image to display, '
                'e.g. "/static/map.png".'
            ))

        if "max_clicks" in q:
            mc = q["max_clicks"]
            if not isinstance(mc, int) or isinstance(mc, bool) or mc < 0:
                results.append(ValidationResult(
                    "error", filename,
                    f"Question #{i+1} ('image_click'): 'max_clicks' must be a "
                    f"non-negative integer (got {mc!r}).",
                    "Use 1 for single-click, an integer >1 to cap multi-click, "
                    "or 0 for unlimited clicks."
                ))

        if "width" in q:
            w = q["width"]
            if not isinstance(w, int) or isinstance(w, bool) or w <= 0:
                results.append(ValidationResult(
                    "error", filename,
                    f"Question #{i+1} ('image_click'): 'width' must be a "
                    f"positive integer pixel value (got {w!r}).",
                    'Set "width" to an integer like 600 to cap the displayed '
                    "image width."
                ))

    return results


def validate_show_if(json_data: dict, filename: str) -> list[ValidationResult]:
    """Check that any per-question ``show_if`` predicates parse cleanly and
    only reference field IDs declared on this questionnaire."""
    results = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return results

    # Local import keeps this module loadable even if the expressions package
    # has not yet been initialised (e.g. during a partial install).
    from BOFS.expressions import (
        ExpressionError,
        parse_with_field_ids,
        referenced_fields,
    )

    known_ids = {fid for fid, _ in _collect_field_ids(json_data)}

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        expr = q.get("show_if")
        if expr is None:
            continue
        if not isinstance(expr, str) or not expr.strip():
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} has a non-string show_if "
                f"({type(expr).__name__}).",
                "show_if must be an expression string, e.g. \"age >= 18\"."
            ))
            continue

        try:
            ast = parse_with_field_ids(expr, list(known_ids))
        except ExpressionError as e:
            results.append(ValidationResult(
                "error", filename,
                f"Question #{i+1} has an unparseable show_if: `{expr}`. {e}",
                "Use a Python-like expression, e.g. \"age < 18 and country in ['US', 'CA']\"."
            ))
            continue

        unknown = referenced_fields(ast) - known_ids
        if unknown:
            results.append(ValidationResult(
                "warning", filename,
                f"Question #{i+1} show_if references unknown fields: "
                f"{', '.join(sorted(unknown))}.",
                f"Known field IDs in this questionnaire: "
                f"{', '.join(sorted(known_ids)) or '(none)'}. "
                f"Check for typos."
            ))

    return results


def validate_calculations(json_data: dict, filename: str) -> list[ValidationResult]:
    """Check participant_calculations for SQL-safe names and valid field references."""
    results = []
    calcs = json_data.get("participant_calculations")

    if calcs is None:
        return results

    if not isinstance(calcs, dict):
        results.append(ValidationResult(
            "error", filename,
            f"'participant_calculations' must be a JSON object, got {type(calcs).__name__}.",
        ))
        return results

    # Collect known field IDs
    known_ids = {fid for fid, _ in _collect_field_ids(json_data)}

    for calc_name, calc_expr in calcs.items():
        # Check calc field name is SQL-safe
        if not is_sql_safe(calc_name):
            results.append(ValidationResult(
                "error", filename,
                f"Calculated field name '{calc_name}' is not a valid identifier.",
                "Names must start with a letter or underscore, and contain only letters, "
                "numbers, and underscores."
            ))
        elif keyword.iskeyword(calc_name):
            results.append(ValidationResult(
                "error", filename,
                f"Calculated field name '{calc_name}' is a Python keyword.",
                f"Calculated values are read via attribute access "
                f"(e.g. participant.questionnaire('{filename}').{calc_name}), "
                f"which is a syntax error for keywords. Choose a different name."
            ))

        if calc_name in RESERVED_COLUMNS:
            results.append(ValidationResult(
                "error", filename,
                f"Calculated field name '{calc_name}' conflicts with a reserved BOFS column.",
                f"Reserved names: {', '.join(sorted(RESERVED_COLUMNS))}. Choose a different name."
            ))
        elif calc_name in RESERVED_EXPRESSION_NAMES:
            results.append(ValidationResult(
                "error", filename,
                f"Calculated field name '{calc_name}' conflicts with a reserved expression name.",
                f"'{calc_name}' is reserved for use in show_if and "
                f"participant_calculations expressions. Choose a different name."
            ))

        if not isinstance(calc_expr, str):
            results.append(ValidationResult(
                "error", filename,
                f"Calculation for '{calc_name}' must be a string expression, got {type(calc_expr).__name__}.",
            ))
            continue

        # Parse the expression and check that every referenced identifier
        # is either a question field ID, another calculated field on this
        # same questionnaire (calcs are added as methods on the row
        # class, so cross-calc references resolve at runtime), or one of
        # the participant-level reserved bare names. Function-call names
        # are validated by the parser whitelist, so they don't appear in
        # referenced_fields(ast) and never trigger this warning.
        from BOFS.expressions import ExpressionError, parse_with_field_ids, referenced_fields
        from BOFS.expressions.participant_env import RESERVED_PARTICIPANT_BARE_NAMES

        all_calc_names = set(calcs.keys()) if isinstance(calcs, dict) else set()
        known_in_scope = known_ids | all_calc_names | set(RESERVED_PARTICIPANT_BARE_NAMES)

        try:
            calc_ast = parse_with_field_ids(calc_expr, list(known_in_scope))
        except ExpressionError:
            # The expression doesn't parse under the BOFS DSL. The fatal
            # parser failure is already reported elsewhere
            # (JSONQuestionnaire.create_db_class raises at startup); skip
            # the reference check rather than producing a noisy second
            # warning on top.
            continue

        unknown = sorted(referenced_fields(calc_ast) - known_in_scope)
        if unknown:
            results.append(ValidationResult(
                "warning", filename,
                f"Calculated field '{calc_name}' references unknown identifiers: "
                f"{', '.join(unknown)}.",
                f"Known field IDs in this questionnaire: "
                f"{', '.join(sorted(known_ids)) or '(none)'}. "
                f"Check for typos in your calculation expression."
            ))

    return results


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def validate_database_binding(json_data: dict, filename: str,
                              available_binds) -> list[ValidationResult]:
    """Reject ``database`` values that aren't keys in ``SQLALCHEMY_BINDS``.

    A typo here would silently send rows to the default DB instead of the
    intended (often PII-isolated) bind, so this is a fatal validation error
    rather than a warning.

    :param available_binds: An iterable (typically a set) of configured bind
        names. Pass an empty set when ``SQLALCHEMY_BINDS`` is unset.
    """
    if not isinstance(json_data, dict):
        return []

    if "database" not in json_data:
        return []

    value = json_data["database"]
    if value is None or value == "":
        # Treat explicit null / empty as "use default bind" — same as omitting
        # the field. No error.
        return []

    available_set = set(available_binds)

    if not isinstance(value, str):
        return [ValidationResult(
            "error", filename,
            f"'database' must be a string naming an entry in "
            f"SQLALCHEMY_BINDS, got {type(value).__name__}.",
            f"Configured binds: {sorted(available_set) or '(none)'}. "
            f"Remove the 'database' field to use the default DB."
        )]

    if value not in available_set:
        if not available_set:
            # Distinct message when SQLALCHEMY_BINDS is missing entirely —
            # otherwise the "is not a configured bind" wording reads as if
            # the bind list exists and just doesn't contain this one.
            return [ValidationResult(
                "error", filename,
                f"'database' is set to {value!r} but no [SQLALCHEMY_BINDS] "
                f"block is configured.",
                f"Add a [SQLALCHEMY_BINDS] table to your config.toml with "
                f"{value!r} as a key (e.g. {value} = \"sqlite:///{value}.db\"), "
                f"or remove the 'database' field to use the default DB."
            )]
        return [ValidationResult(
            "error", filename,
            f"'database' value {value!r} is not a configured bind.",
            f"Configured binds: {sorted(available_set)}. "
            f"Add {value!r} to [SQLALCHEMY_BINDS] in your config, or remove "
            f"the 'database' field to use the default DB."
        )]

    return []


def validate_questionnaire(json_data: dict, filename: str,
                           valid_types: frozenset = None,
                           available_binds=frozenset()) -> list[ValidationResult]:
    """
    Run all validations on a single questionnaire's JSON data.
    Returns a list of ValidationResult objects (may be empty if everything is valid).
    """
    results = []

    # Structure check first — if it fails, other checks can't proceed
    structure_results = validate_structure(json_data, filename)
    results.extend(structure_results)
    if any(r.severity == "error" for r in structure_results):
        return results

    results.extend(validate_question_types(json_data, filename, valid_types))
    results.extend(validate_question_ids(json_data, filename))
    results.extend(validate_field_ids(json_data, filename))
    results.extend(validate_image_select(json_data, filename))
    results.extend(validate_image_click(json_data, filename))
    results.extend(validate_calculations(json_data, filename))
    results.extend(validate_show_if(json_data, filename))
    results.extend(validate_database_binding(json_data, filename, available_binds))

    return results


def validate_db_schema(questionnaire, filename: str) -> list[ValidationResult]:
    """
    Check for mismatches between the database table and the questionnaire JSON definition.

    Reads orphaned column and type mismatch info populated by
    JSONQuestionnaire.create_db_class() during startup.

    :param questionnaire: A JSONQuestionnaire instance (after create_db_class() has been called).
    :param filename: The questionnaire filename (for error messages).
    :return: List of ValidationResult warnings.
    """
    results = []

    orphaned = getattr(questionnaire, '_orphaned_columns', None) or []
    type_mismatches = getattr(questionnaire, '_type_mismatches', None) or []

    for col_info in orphaned:
        col_name = col_info['name']
        # Informational: BOFS preserves the old data and writes NULL
        # for new submissions. Nothing is broken — the column is just
        # carrying historical data that the current JSON no longer
        # describes. Surface so the researcher knows, but don't flag.
        results.append(ValidationResult(
            "info", filename,
            f"Column '{col_name}' exists in the database but is no longer defined "
            f"in the questionnaire. It was likely renamed or removed.",
            f"Old data in this column is preserved. New submissions will have NULL "
            f"for this column. If this is not what you want, consider deleting the "
            f"database and re-collecting data."
        ))

    for mismatch in type_mismatches:
        results.append(ValidationResult(
            "warning", filename,
            f"Column '{mismatch['field_id']}' has type {mismatch['db_type']} in the "
            f"database but is now defined as '{mismatch['json_type']}' in the JSON.",
            "SQLite may handle this automatically, but data types could be "
            "inconsistent between old and new responses."
        ))

    return results


def validate_table(json_data: dict, filename: str,
                   available_binds=frozenset()) -> list[ValidationResult]:
    """Validate a JSONTable JSON file.

    Checks:

    * Column names are SQL-safe and aren't Python keywords (researchers
      read row values via attribute access, e.g. ``row.field``).
    * Export field names don't collide with column names on the same
      table — the ``TableAccessor`` resolves bare attribute access to
      exports, so a colliding name would shadow the row column when
      researchers write ``participant.table('foo').<name>``.
    * Export field names are SQL-safe and aren't Python keywords.
    """
    results = []

    if not isinstance(json_data, dict):
        return results

    # Bind validation runs first so it isn't masked by an early return below
    # (e.g. when the table has no exports). Researcher-visible errors should
    # surface together rather than in a second pass.
    results.extend(validate_database_binding(json_data, filename, available_binds))

    columns = json_data.get("columns")
    if columns is None:
        columns = {}
    elif not isinstance(columns, dict):
        results.append(ValidationResult(
            "error", filename,
            f"'columns' must be a JSON object, got "
            f"{type(columns).__name__}.",
        ))
        columns = {}

    column_names = set(columns.keys())

    for col_name in columns:
        if not isinstance(col_name, str):
            continue
        if not is_sql_safe(col_name):
            results.append(ValidationResult(
                "error", filename,
                f"Column name '{col_name}' is not a valid identifier.",
                "Names must start with a letter or underscore, and contain only "
                "letters, numbers, and underscores."
            ))
        elif keyword.iskeyword(col_name):
            results.append(ValidationResult(
                "error", filename,
                f"Column name '{col_name}' is a Python keyword.",
                f"Templates read row values via attribute access "
                f"(e.g. row.{col_name}), which is a syntax error for "
                f"keywords. Choose a different name."
            ))

    exports = json_data.get("exports")
    if exports is None:
        return results
    if not isinstance(exports, list):
        results.append(ValidationResult(
            "error", filename,
            f"'exports' must be a JSON array, got {type(exports).__name__}.",
        ))
        return results

    for i, export in enumerate(exports):
        if not isinstance(export, dict):
            continue
        fields = export.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        for field_name, field_expr in fields.items():
            if not isinstance(field_name, str):
                continue
            if not is_sql_safe(field_name):
                results.append(ValidationResult(
                    "error", filename,
                    f"Export field name '{field_name}' "
                    f"(exports[{i}]) is not a valid identifier.",
                    "Names must start with a letter or underscore, and contain "
                    "only letters, numbers, and underscores."
                ))
                continue
            if keyword.iskeyword(field_name):
                results.append(ValidationResult(
                    "error", filename,
                    f"Export field name '{field_name}' "
                    f"(exports[{i}]) is a Python keyword.",
                    f"Templates read aggregate values via attribute access "
                    f"(e.g. participant.table('{filename}').{field_name}), "
                    f"which is a syntax error for keywords. Choose a "
                    f"different name."
                ))
                continue
            if field_name in column_names:
                results.append(ValidationResult(
                    "error", filename,
                    f"Export field name '{field_name}' "
                    f"(exports[{i}]) collides with a column of the same "
                    f"name on this table.",
                    f"participant.table('{filename}').{field_name} would "
                    f"resolve to the export aggregate and shadow the raw "
                    f"column. Rename either the column or the export."
                ))
                continue
            # Validate the SQL expression — wrapped in db.literal_column at
            # query-build time, so a string like "0; DROP TABLE x; --" would
            # interpolate verbatim into the SELECT list.
            ok, why = is_sql_expression_safe(field_expr)
            if not ok:
                results.append(ValidationResult(
                    "error", filename,
                    f"Export field '{field_name}' (exports[{i}]) has an "
                    f"invalid SQL expression: {why}.",
                    "Expressions may use column names, numbers, single-quoted "
                    "strings, comparison/arithmetic operators, and the "
                    "functions: "
                    + ", ".join(sorted(_SQL_EXPR_FUNCTIONS))
                    + ". Example: \"avg(case when correct then 1.0 else 0.0 end)\"."
                ))

        for clause in ("filter", "having"):
            expr = export.get(clause)
            if expr in (None, ""):
                continue
            ok, why = is_sql_expression_safe(expr)
            if not ok:
                results.append(ValidationResult(
                    "error", filename,
                    f"Export '{clause}' clause (exports[{i}]) is invalid: {why}.",
                    f"The {clause} expression must use only column names, "
                    f"literals, and the allow-listed operators/functions. "
                    f"Example: \"phase = 'learning'\"."
                ))

    return results


def _collect_subscripted_var_names(ast_node) -> set:
    """Walk a parsed expression AST and return the set of ``var`` names
    that appear as the container of a ``subscript`` node.

    Used by :func:`validate_page_show_if_table_refs` to suppress the
    group_by warning when the author has subscripted the placeholder
    via bracket form (``tables.X.Y[<key>]``) rather than dotted form
    (``tables.X.Y.<key>``).
    """
    found = set()

    def walk(node):
        if isinstance(node, dict):
            sub = node.get("subscript")
            if isinstance(sub, dict) and "var" in sub:
                found.add(sub["var"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(ast_node)
    return found


def validate_page_show_if_table_refs(page_list, tables) -> list[ValidationResult]:
    """Walk a PageList's compiled show_if expressions and warn about any
    ``tables.<name>.<column>`` reference that doesn't resolve to a known
    table export.

    Visits page entries, ``conditional_routing`` arms (which can carry an
    arm-level ``show_if``), and the inner pages within each arm.

    :param page_list: a list of page entries that have already passed
        through :meth:`PageList._compile_show_if` (so each entry has its
        ``_show_if_refs`` attached).
    :param tables: dict ``{filename: JSONTable}``, typically
        ``current_app.tables``.
    """
    results = []

    def label_for(entry):
        return entry.get("name", entry.get("path", "<unnamed>"))

    def check_refs(entry, source_label):
        refs = entry.get("_show_if_refs") or {}
        ast_node = entry.get("_show_if_ast")
        subscripted_placeholders = _collect_subscripted_var_names(ast_node)
        for placeholder, spec in refs.items():
            if spec.get("kind") != "table":
                continue
            tname = spec["tname"]
            column = spec["column"]
            table = tables.get(tname)
            if table is None:
                results.append(ValidationResult(
                    "warning", "PAGE_LIST",
                    f"show_if on {source_label} "
                    f"references unknown table 'tables.{tname}'.",
                    f"Known tables: "
                    f"{', '.join(sorted(tables)) or '(none)'}."
                ))
                continue

            exports = table.create_exports_dict() or []
            known_columns = set()
            group_by_columns = set()
            for export in exports:
                fields = export.get("fields") or {}
                known_columns.update(fields.keys())
                if export.get("group_by"):
                    group_by_columns.update(fields.keys())
            if column not in known_columns:
                results.append(ValidationResult(
                    "warning", "PAGE_LIST",
                    f"show_if on {source_label} "
                    f"references unknown column "
                    f"'tables.{tname}.{column}'.",
                    f"Known export columns on '{tname}': "
                    f"{', '.join(sorted(known_columns)) or '(none)'}."
                ))
            elif column in group_by_columns:
                # The ref is unambiguous (and thus warning-free) when the
                # author has either supplied a literal dotted key
                # (``tables.X.Y.<key>``) or applied a bracket subscript
                # (``tables.X.Y[<expr>]``). Either path resolves to a
                # single scalar at evaluation time.
                if spec.get("key") is not None:
                    continue
                if placeholder in subscripted_placeholders:
                    continue
                results.append(ValidationResult(
                    "warning", "PAGE_LIST",
                    f"show_if on {source_label} "
                    f"references 'tables.{tname}.{column}', which is "
                    f"defined under a group_by export and produces "
                    f"multiple values per participant.",
                    f"Page-level show_if can only consume scalar "
                    f"aggregates. Subscript into the dict "
                    f"(``tables.{tname}.{column}[<key>]`` or "
                    f"``tables.{tname}.{column}.<key>``), reference one "
                    f"of the level-suffixed columns directly in the data "
                    f"export, or read the per-level dict from "
                    f"participant.table('{tname}').{column} in a "
                    f"template or custom blueprint."
                ))

    def visit(entries):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if "conditional_routing" in entry:
                for cr in entry["conditional_routing"]:
                    check_refs(
                        cr,
                        f"conditional_routing arm "
                        f"(condition={cr.get('condition')!r})",
                    )
                    visit(cr.get("page_list", []))
                continue
            check_refs(entry, f"page {label_for(entry)!r}")

    visit(page_list)
    return results


def validate_page_list_references(page_list_data: list,
                                  questionnaire_paths: dict) -> list[ValidationResult]:
    """
    Check that every questionnaire referenced in PAGE_LIST has a matching JSON file.

    :param page_list_data: the raw PAGE_LIST from config (list of dicts)
    :param questionnaire_paths: dict from BOFSFlask.find_files_in_app_and_blueprints(),
        mapping directory paths to lists of questionnaire filenames (without .json)
    """
    results = []

    # Flatten all known questionnaire filenames
    known_questionnaires = set()
    for path, filenames in questionnaire_paths.items():
        known_questionnaires.update(filenames)

    # Walk PAGE_LIST (including inside conditional_routing blocks)
    def extract_questionnaire_refs(pages):
        refs = []
        for page in pages:
            if isinstance(page, dict):
                if "path" in page:
                    path = page["path"]
                    if isinstance(path, str) and path.startswith("questionnaire/"):
                        # Extract questionnaire name (strip tag if present)
                        q_name = path.replace("questionnaire/", "", 1).split("/")[0]
                        refs.append(q_name)
                if "conditional_routing" in page:
                    for route in page["conditional_routing"]:
                        if isinstance(route, dict) and "page_list" in route:
                            refs.extend(extract_questionnaire_refs(route["page_list"]))
        return refs

    referenced = extract_questionnaire_refs(page_list_data)

    for q_name in referenced:
        if q_name not in known_questionnaires:
            results.append(ValidationResult(
                "error", "PAGE_LIST",
                f"Questionnaire '{q_name}' is referenced in PAGE_LIST but no "
                f"matching '{q_name}.json' file was found.",
                "Check for typos in the questionnaire path, or create the missing "
                f"'{q_name}.json' file in your questionnaires/ folder."
            ))

    return results


# ---------------------------------------------------------------------------
# Post-load (cross-file) validation passes
# ---------------------------------------------------------------------------
#
# These checks run after every questionnaire and table has been loaded so
# they can reason about the global namespace of field IDs, table exports,
# and project asset directories. The per-file ``validate_questionnaire`` /
# ``validate_table`` passes can't see across files, so they would either
# false-positive (cross-questionnaire ``show_if`` references) or miss the
# check entirely (missing image assets, empty files).


def validate_table_not_empty(table, filename: str) -> list:
    """Warn when a loaded table defines zero columns. Same rationale as
    :func:`validate_questionnaire_not_empty`."""
    json_data = getattr(table, "json_data", None) or {}
    columns = json_data.get("columns")
    if not isinstance(columns, dict) or len(columns) == 0:
        return [ValidationResult(
            "warning", filename,
            f"Table '{filename}' has no columns defined.",
            "Add at least one entry to the 'columns' object, or remove "
            "the table if it isn't needed."
        )]
    return []


def _collect_image_asset_refs(json_data: dict) -> list[tuple[int, str, str]]:
    """Return ``(question_index, question_type, src)`` tuples for every
    image referenced by an ``image_select`` or ``image_click`` question.

    ``image_select`` has a list of ``{src, value, label}`` images; the
    src of each is extracted. ``image_click`` has a single top-level
    ``src``.
    """
    refs: list[tuple[int, str, str]] = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return refs
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        qtype = q.get("questiontype")
        if qtype == "image_select":
            images = q.get("images")
            if isinstance(images, list):
                for img in images:
                    if isinstance(img, dict):
                        src = img.get("src")
                        if isinstance(src, str) and src:
                            refs.append((i, qtype, src))
        elif qtype == "image_click":
            src = q.get("src")
            if isinstance(src, str) and src:
                refs.append((i, qtype, src))
    return refs


def _resolve_asset_candidate_paths(src: str, project_root: str,
                                   bofs_path: str) -> list[str]:
    """Build the list of on-disk paths to probe for an image reference.

    BOFS serves images via Flask's static system. A researcher writes
    ``/static/foo.png`` (project static) or ``/BOFS_static/foo.png``
    (BOFS-bundled static) in their JSON, plus a few historical forms.
    Anything starting with ``http(s)://`` or ``//`` is treated as an
    external URL and not checked.
    """
    if not src:
        return []
    if src.startswith(("http://", "https://", "//", "data:")):
        return []  # Remote / data URI — out of scope for an asset check.

    # Normalise the leading slash before mapping to a filesystem prefix.
    clean = src.lstrip("/")

    candidates: list[str] = []
    # /static/foo.png -> <project>/static/foo.png
    if clean.startswith("static/"):
        candidates.append(os.path.join(project_root, clean))
    # /BOFS_static/foo.png -> <bofs_path>/static/foo.png
    if clean.startswith("BOFS_static/"):
        candidates.append(os.path.join(
            bofs_path, "static", clean[len("BOFS_static/"):]
        ))
    # Bare path: try project root first, then BOFS static.
    if not (clean.startswith("static/") or clean.startswith("BOFS_static/")):
        candidates.append(os.path.join(project_root, clean))
        candidates.append(os.path.join(project_root, "static", clean))
        candidates.append(os.path.join(bofs_path, "static", clean))

    return candidates


def validate_image_assets(questionnaire, filename: str,
                          project_root: str, bofs_path: str) -> list:
    """For every ``image_select`` / ``image_click`` reference, check that
    the file actually exists on disk in one of the locations BOFS would
    serve from.

    External URLs (``http://``, ``https://``, protocol-relative ``//``,
    ``data:``) are skipped — BOFS doesn't fetch them, so the check can't
    apply, and false-positives here would be noisy on every startup.
    """
    results = []
    json_data = getattr(questionnaire, "json_data", None) or {}
    for i, qtype, src in _collect_image_asset_refs(json_data):
        candidates = _resolve_asset_candidate_paths(src, project_root, bofs_path)
        if not candidates:
            continue  # Remote / non-checkable
        if any(os.path.isfile(p) for p in candidates):
            continue
        results.append(ValidationResult(
            "warning", filename,
            f"Question #{i+1} ({qtype}) references image {src!r} but no "
            f"matching file was found.",
            "Check the path against your project's static/ folder. "
            f"Looked in: {', '.join(repr(p) for p in candidates)}."
        ))
    return results


def _build_global_field_namespace(questionnaires, tables) -> set:
    """Union of every identifier a page-level ``show_if`` predicate may
    legally reference as a bare name.

    Includes: questionnaire field IDs (from every loaded questionnaire),
    participant_calculations names, RESERVED_PARTICIPANT_BARE_NAMES
    (``condition``, ``source``, ``end_reason``), and the literal name
    ``tables`` (so a predicate that references ``tables.x.y`` without
    being parsed via the dotted-replacement path can still resolve).
    """
    from .expressions.participant_env import RESERVED_PARTICIPANT_BARE_NAMES

    names: set = set(RESERVED_PARTICIPANT_BARE_NAMES)
    names.add("tables")
    for qname, q in (questionnaires or {}).items():
        try:
            for f in q.fetch_fields():
                names.add(f.id)
        except Exception:
            # Questionnaire may not be DB-ready yet (e.g. skipped because
            # of fatal validation errors). Pull from json_data as a
            # fallback so the namespace stays inclusive.
            for fid, _ in _collect_field_ids(getattr(q, "json_data", {}) or {}):
                names.add(fid)
        calcs = (getattr(q, "json_data", {}) or {}).get("participant_calculations")
        if isinstance(calcs, dict):
            names.update(calcs.keys())
    return names


def validate_page_list_show_if_refs(page_list, questionnaires,
                                    tables) -> list:
    """Cross-file check: page-level ``show_if`` predicates and
    ``conditional_routing`` arm predicates reference identifiers that
    exist somewhere in the loaded project.

    Page-level predicates can reference fields from any questionnaire
    the participant has already submitted (or will submit later in the
    same flow) plus the reserved bare names. The within-questionnaire
    ``validate_show_if`` pass can't see that broader namespace, so it
    isn't used for these predicates — this function fills the gap.

    The per-table reference check (``tables.<name>.<column>``) is
    handled separately by :func:`validate_page_show_if_table_refs`.
    """
    results = []
    known = _build_global_field_namespace(questionnaires, tables)

    def label_for(entry):
        return entry.get("name", entry.get("path", "<unnamed>"))

    def check_entry(entry, source_label):
        ast = entry.get("_show_if_ast")
        if ast is None:
            return
        from BOFS.expressions import referenced_fields
        refs = entry.get("_show_if_refs") or {}
        all_refs = referenced_fields(ast)
        bare_refs = all_refs - set(refs)
        unknown_bare = sorted(bare_refs - known)
        if unknown_bare:
            results.append(ValidationResult(
                "warning", "PAGE_LIST",
                f"show_if on {source_label} references unknown identifier(s): "
                f"{', '.join(unknown_bare)}.",
                "Check for typos. The reference must be a questionnaire "
                "field ID, a participant_calculations name, or one of "
                "'condition', 'source', 'end_reason'."
            ))

        # Validate dotted ``qname.tag.field`` placeholders that resolve
        # to a specific questionnaire row. Table refs are checked in
        # validate_page_show_if_table_refs.
        for placeholder, spec in refs.items():
            if spec.get("kind") != "questionnaire":
                continue
            qname = spec.get("qname")
            field = spec.get("field")
            q = (questionnaires or {}).get(qname)
            if q is None:
                results.append(ValidationResult(
                    "warning", "PAGE_LIST",
                    f"show_if on {source_label} references "
                    f"'{spec.get('source', qname)}' but no questionnaire "
                    f"named {qname!r} is loaded.",
                    f"Known questionnaires: "
                    f"{', '.join(sorted(questionnaires or {})) or '(none)'}."
                ))
                continue
            try:
                field_ids = {f.id for f in q.fetch_fields()}
            except Exception:
                field_ids = {fid for fid, _ in _collect_field_ids(
                    getattr(q, "json_data", {}) or {}
                )}
            calcs = (getattr(q, "json_data", {}) or {}).get("participant_calculations")
            if isinstance(calcs, dict):
                field_ids |= set(calcs.keys())
            if field not in field_ids:
                results.append(ValidationResult(
                    "warning", "PAGE_LIST",
                    f"show_if on {source_label} references "
                    f"'{spec.get('source')}', but {field!r} is not a "
                    f"known field on questionnaire {qname!r}.",
                    f"Known fields on {qname!r}: "
                    f"{', '.join(sorted(field_ids)) or '(none)'}."
                ))

    def visit(entries):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if "conditional_routing" in entry:
                for cr in entry["conditional_routing"]:
                    check_entry(
                        cr,
                        f"conditional_routing arm "
                        f"(condition={cr.get('condition')!r})",
                    )
                    visit(cr.get("page_list", []))
                continue
            check_entry(entry, f"page {label_for(entry)!r}")

    visit(page_list)
    return results
