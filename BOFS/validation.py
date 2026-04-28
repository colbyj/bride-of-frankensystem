"""
Validation module for BOFS questionnaire JSON files.

Provides pure validation functions that check questionnaire structure,
field IDs, question types, and calculated fields. Used both at startup
(to show helpful error pages) and in the test suite.
"""

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

# Question types whose top-level `id` expands into multiple suffixed columns.
# Maps questiontype -> list of (suffix, datatype) pairs.
EXPANDED_TYPES = {
    "video": [("_started", "float"), ("_ended", "float"), ("_watched", "float")],
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

# Regex for SQL-safe identifiers: letter or underscore, then alphanumeric/underscore
_SQL_SAFE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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
        prefix = "ERROR" if self.severity == "error" else "WARNING"
        s = f"  {prefix} in '{self.questionnaire}': {self.message}"
        if self.suggestion:
            s += f"\n    -> {self.suggestion}"
        return s

    def __repr__(self):
        return f"ValidationResult({self.severity!r}, {self.questionnaire!r}, {self.message!r})"


def is_sql_safe(name: str) -> bool:
    """Check if a string is a valid SQL column identifier."""
    return bool(_SQL_SAFE_RE.match(name))


def _collect_field_ids(json_data: dict) -> list[tuple[str, int]]:
    """
    Walk the questions list and return (field_id, question_index) pairs,
    mirroring the logic in JSONQuestionnaire.fetch_fields().
    """
    ids = []
    questions = json_data.get("questions", [])
    if not isinstance(questions, list):
        return ids

    for i, q in enumerate(questions):
        # Nested questions (radiogrid, checklist, etc.)
        nested = q.get("questions") or q.get("q_text")
        if isinstance(nested, list):
            for sub in nested:
                if isinstance(sub, dict) and "id" in sub:
                    ids.append((sub["id"], i))

        # Top-level ID
        if "id" in q:
            qtype = q.get("questiontype")
            if qtype in EXPANDED_TYPES and isinstance(q["id"], str):
                for suffix, _dtype in EXPANDED_TYPES[qtype]:
                    ids.append((q["id"] + suffix, i))
            else:
                ids.append((q["id"], i))

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

    return results


def validate_question_ids(json_data: dict, filename: str) -> list[ValidationResult]:
    """
    Check that non-display questions have IDs, and that questions which
    use nested sub-questions (radiogrid, checklist) have IDs on those sub-items.
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

        if calc_name in RESERVED_COLUMNS:
            results.append(ValidationResult(
                "error", filename,
                f"Calculated field name '{calc_name}' conflicts with a reserved BOFS column.",
                f"Reserved names: {', '.join(sorted(RESERVED_COLUMNS))}. Choose a different name."
            ))

        if not isinstance(calc_expr, str):
            results.append(ValidationResult(
                "error", filename,
                f"Calculation for '{calc_name}' must be a string expression, got {type(calc_expr).__name__}.",
            ))
            continue

        # Extract word tokens from the expression and check against known field IDs.
        # Tokens that look like identifiers but aren't known fields or Python builtins
        # are flagged as warnings (not errors, since they could be valid Python names).
        tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", calc_expr))
        # Common functions/builtins used in calculations
        safe_tokens = {"mean", "sum", "min", "max", "abs", "float", "int", "len",
                       "round", "self", "getattr", "True", "False", "None"}
        unknown = tokens - known_ids - safe_tokens
        if unknown:
            results.append(ValidationResult(
                "warning", filename,
                f"Calculated field '{calc_name}' references unknown identifiers: "
                f"{', '.join(sorted(unknown))}.",
                f"Known field IDs in this questionnaire: {', '.join(sorted(known_ids)) or '(none)'}. "
                f"Check for typos in your calculation expression."
            ))

    return results


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def validate_questionnaire(json_data: dict, filename: str,
                           valid_types: frozenset = None) -> list[ValidationResult]:
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
    results.extend(validate_calculations(json_data, filename))

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
        results.append(ValidationResult(
            "warning", filename,
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
