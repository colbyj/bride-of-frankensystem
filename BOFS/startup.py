"""Startup-time helpers for BOFS.

Operations that run once during application construction: loading the
project config, discovering and loading blueprints, loading questionnaire
and table JSON definitions, resolving the persisted ``SECRET_KEY``, and
emitting startup warnings about misconfigured routes.

Functions here take a :class:`~BOFS.BOFSFlask.BOFSFlask` instance as their
first argument. Each is also exposed as a thin pass-through method on
``BOFSFlask`` so existing callers (including researcher blueprints) that
write ``app.load_questionnaire(...)`` continue to work; new code should
prefer importing from this module directly.
"""

import json
import os
import secrets
from typing import Union

import toml
from flask import Blueprint

from .JSONQuestionnaire import JSONQuestionnaire
from .JSONTable import JSONTable


# Pages whose view functions are framework-special and don't go through
# @verify_correct_page (handled in the admin timeline as a special case).
_PAGES_DECORATOR_NOT_REQUIRED = frozenset({
    'consent', 'consent_nc', 'create_participant', 'create_participant_nc', 'end',
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(app, filename: str, silent: bool = False) -> None:
    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"Configuration file not found: '{filename}'\n"
            f"Make sure the file exists and you're running BOFS from the correct directory."
        )

    if filename.endswith(".cfg"):
        app.config.from_pyfile(filename, silent=silent)
    elif filename.endswith(".toml"):
        try:
            app.config.from_file(filename, load=toml.load)
        except toml.TomlDecodeError as e:
            raise ValueError(f"Invalid TOML syntax in '{filename}': {e}")
    elif filename.endswith(".json"):
        try:
            app.config.from_file(filename, load=json.load)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON syntax in '{filename}': {e}")
    else:
        raise ValueError(
            f"Unsupported configuration file format: '{filename}'\n"
            f"BOFS supports .toml, .json, and .cfg configuration files."
        )


def resolve_secret_key(app) -> None:
    """Load SECRET_KEY from the app_meta table, or generate and persist one.

    Honours a SECRET_KEY supplied in the project config (legacy behaviour):
    the value is seeded into app_meta on first run with a one-time notice.
    On subsequent runs the database value is the source of truth — the
    config line is ignored, and a notice is printed reminding the
    researcher to remove it.
    """
    config_key = app.config.get('SECRET_KEY')
    stored = app.db.session.get(app.db.AppMeta, 'secret_key')

    if stored is None:
        if config_key:
            app.db.session.add(app.db.AppMeta(key='secret_key', value=config_key))
            app.db.session.commit()
            # First-run migration: informational, not actionable yet.
            print(
                "NOTE: SECRET_KEY in your config has been migrated into the project database. "
                "BOFS now manages SECRET_KEY automatically — you can safely remove the line "
                "from your .toml config file."
            )
            app.setup_diagnostics.add(
                "warning", "security",
                "SECRET_KEY is set in your config; BOFS has migrated it "
                "into the project database and now manages it automatically.",
                suggestion="Remove the SECRET_KEY line from your config.toml.",
                source="SECRET_KEY",
            )
        else:
            new_key = secrets.token_hex(32)
            app.db.session.add(app.db.AppMeta(key='secret_key', value=new_key))
            app.db.session.commit()
            app.config['SECRET_KEY'] = new_key
        return

    # Stored value already exists — it is the source of truth.
    if config_key and config_key != stored.value:
        app.setup_diagnostics.add(
            "warning", "security",
            "SECRET_KEY is set in your config but BOFS is using the "
            "value persisted in the project database. The config line is "
            "ignored.",
            suggestion="Remove the SECRET_KEY line from your config.toml.",
            source="SECRET_KEY",
        )
    app.config['SECRET_KEY'] = stored.value


# ---------------------------------------------------------------------------
# Blueprint loading
# ---------------------------------------------------------------------------

def load_empty_blueprint(app, blueprint_path: str) -> None:
    print("Creating empty blueprint: %s" % blueprint_path)

    blueprint_var = Blueprint(blueprint_path, blueprint_path,
                              static_url_path='/' + blueprint_path,
                              template_folder=os.path.join(blueprint_path, 'templates'),
                              static_folder=os.path.join(blueprint_path, 'static'))

    app.register_blueprint(blueprint_var)


def load_blueprint(app, blueprint_path: str, blueprint_name=None,
                   try_to_load_models: bool = True) -> None:
    print("Loaded blueprint: %s" % blueprint_path)

    if blueprint_name is None:
        blueprint_name = blueprint_path

    blueprint = __import__(blueprint_path + ".views", fromlist=["views"])
    blueprint_var = getattr(blueprint, blueprint_name)
    app.register_blueprint(blueprint_var)

    if 'DEFAULT_FIELD_WIDTH' not in app.config:
        app.config['DEFAULT_FIELD_WIDTH'] = 400

    if 'ADDITIONAL_ADMIN_PAGES' not in app.config:
        app.config['ADDITIONAL_ADMIN_PAGES'] = []

    if hasattr(blueprint, 'ADDITIONAL_ADMIN_PAGES'):
        app.config['ADDITIONAL_ADMIN_PAGES'].append(blueprint.ADDITIONAL_ADMIN_PAGES)

    if 'EXPORT' not in app.config:
        app.config['EXPORT'] = []

    if hasattr(blueprint, 'EXPORT'):
        app.config['EXPORT'].extend(blueprint.EXPORT)

    if try_to_load_models:  # Try to load the models too.
        load_models(app, blueprint_path)


def load_models(app, blueprint_path: str) -> None:
    try:
        module = __import__(blueprint_path + ".models", fromlist=["models"])
        create_function = getattr(module, "create")

        if create_function is None:
            print("Warning: %s.models does not contain a `create()` function! No models will be added.")
            return

        with app.app_context():
            my_classes = create_function(app.db)

        if hasattr(my_classes, '__iter__'):  # A list or tuple was returned
            for c in my_classes:
                setattr(app.db, c.__name__, c)
                if app.run_with_debugging:
                    print("%s: Loaded %s" % (blueprint_path, c))
        else:
            setattr(app.db, my_classes.__name__, my_classes)
            if app.run_with_debugging:
                print("%s: Loaded %s" % (blueprint_path, my_classes))

        print("%s: `models.py` loaded!" % blueprint_path)
    except ImportError:
        print("%s: `models.py` not found. Add a `models.py` file to your blueprint folder use this feature." % blueprint_path)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_files_in_app_and_blueprints(app, folder_name: str,
                                     extension: str = ".json") -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}

    app_path = os.path.join(app.root_path, folder_name)

    if os.path.exists(app_path):  # First find tables from /tables
        for file_name in os.listdir(app_path):
            if file_name.endswith(extension):
                if app_path not in results:
                    results[app_path] = []

                results[app_path].append(file_name.replace(extension, ""))

    # Next find tables from /<blueprint_name>/tables
    for blueprint_name in app.blueprints:
        blueprint_path = os.path.join(app.root_path, blueprint_name, folder_name)

        if os.path.exists(blueprint_path):  # Does this blueprint have a directory we can look through?
            for q in os.listdir(blueprint_path):
                if q.endswith(extension):
                    if blueprint_path not in results:
                        results[blueprint_path] = []

                    results[blueprint_path].append(q.replace(extension, ""))

    return results


# ---------------------------------------------------------------------------
# Table loading
# ---------------------------------------------------------------------------

def load_table(app, directory: str, filename: str) -> Union[JSONTable, None]:
    if filename in app.db.metadata.tables:
        return None

    if filename in app.tables:
        return None

    from .validation import RESERVED_EXPRESSION_NAMES
    if filename in RESERVED_EXPRESSION_NAMES:
        app.setup_diagnostics.add(
            "error", "table",
            f"Table filename '{filename}' conflicts with a reserved "
            f"expression name. Tables and questionnaires cannot be named "
            f"any of: {', '.join(sorted(RESERVED_EXPRESSION_NAMES))}.",
            suggestion=f"Rename '{filename}.json' to something else.",
            questionnaire=filename + ".json",
        )
        return None

    print(f"Loaded table: {directory}/{filename}.json")
    table = JSONTable(directory, filename)

    if table.json_data:
        from .validation import validate_table
        available_binds = set(app.config.get("SQLALCHEMY_BINDS", {}) or {})
        errors = validate_table(table.json_data, filename, available_binds=available_binds)
        fatal = [e for e in errors if e.severity == "error"]
        for entry in errors:
            app.setup_diagnostics.append(entry, category="table")
        if fatal:
            app.logger.warning(
                "Skipping table %r due to %d validation error(s).",
                filename, len(fatal),
            )
            return None

    table.create_db_class()
    exports_dict = table.create_exports_dict()

    if exports_dict is not None:
        app.config['EXPORT'] += exports_dict

    # Add the table as a database class, if it hasn't been added already.
    if not hasattr(app.db, table.db_class.__name__):
        setattr(app.db, table.db_class.__name__, table.db_class)

    app.tables[filename] = table
    return table


def load_tables(app) -> None:
    app.table_paths = find_files_in_app_and_blueprints(app, "tables")

    for path in app.table_paths:
        for table_filename in app.table_paths[path]:
            load_table(app, path, table_filename)


# ---------------------------------------------------------------------------
# Questionnaire loading
# ---------------------------------------------------------------------------

def load_questionnaire(app, directory: str, filename: str, add_to_db: bool = False,
                       valid_question_types=None) -> Union[JSONQuestionnaire, None]:
    from .validation import validate_questionnaire, RESERVED_EXPRESSION_NAMES

    if "questionnaire_" + filename in app.db.metadata.tables:
        return None

    if filename in app.questionnaires:
        return None

    if filename in RESERVED_EXPRESSION_NAMES:
        app.setup_diagnostics.add(
            "error", "questionnaire",
            f"Questionnaire filename '{filename}' conflicts with a "
            f"reserved expression name. Questionnaires and tables cannot "
            f"be named any of: "
            f"{', '.join(sorted(RESERVED_EXPRESSION_NAMES))}.",
            suggestion=f"Rename '{filename}.json' to something else.",
            questionnaire=filename + ".json",
        )
        return None

    # Try to load the JSON file
    try:
        questionnaire = JSONQuestionnaire(directory, filename, add_to_db)
    except (SyntaxError, FileNotFoundError, IOError) as e:
        app.setup_diagnostics.add(
            "error", "questionnaire",
            str(e),
            suggestion="Check that the file exists and contains valid JSON syntax.",
            questionnaire=filename,
        )
        return None

    # Validate the questionnaire JSON before creating the DB class
    available_binds = set(app.config.get("SQLALCHEMY_BINDS", {}) or {})
    errors = validate_questionnaire(
        questionnaire.json_data, filename, valid_question_types,
        available_binds=available_binds,
    )
    fatal_errors = [e for e in errors if e.severity == "error"]
    for entry in errors:
        app.setup_diagnostics.append(entry, category="questionnaire")

    if fatal_errors:
        app.logger.warning(
            "Skipping questionnaire %r due to %d validation error(s).",
            filename, len(fatal_errors),
        )
        return None

    # Validation passed — create the DB class
    print(f"Loaded questionnaire: {filename}, add_to_db={add_to_db}")
    questionnaire.create_db_class()

    if add_to_db:
        setattr(app.db, "Questionnaire" + questionnaire.db_class.__name__, questionnaire.db_class)

    app.questionnaires[filename] = questionnaire
    return questionnaire


def questionnaire_list_is_safe(app) -> bool:
    """Check whether the configured questionnaire list has any duplicates.

    :return: True if a duplicate was found, False otherwise.
    """
    questionnaires = app.page_list.get_questionnaire_list(include_tags=True)
    return len(set(questionnaires)) == len(questionnaires)


def load_questionnaires(app) -> None:
    from .validation import validate_page_list_references, discover_question_types

    app.questionnaire_paths = find_files_in_app_and_blueprints(app, "questionnaires")
    questionnaires_in_use = app.page_list.get_questionnaire_list()

    # Discover all valid question types (built-in + project + blueprints)
    valid_question_types = discover_question_types(app)

    for path in app.questionnaire_paths:
        for questionnaire_filename in app.questionnaire_paths[path]:
            add_to_db = questionnaire_filename in questionnaires_in_use
            load_questionnaire(app, path, questionnaire_filename, add_to_db, valid_question_types)

    # Check that all PAGE_LIST questionnaire references have matching files
    for err in validate_page_list_references(app.config['PAGE_LIST'], app.questionnaire_paths):
        app.setup_diagnostics.append(err, category="page_list")


def get_questionnaire_path(app, questionnaire_to_find: str) -> Union[str, None]:
    for path in app.questionnaire_paths:
        for questionnaire_filename in app.questionnaire_paths[path]:
            if questionnaire_to_find == questionnaire_filename:
                return str(os.path.join(path, questionnaire_filename + ".json"))
    return None


# ---------------------------------------------------------------------------
# Startup warnings
# ---------------------------------------------------------------------------

def warn_about_unused_binds(app) -> None:
    """Warn when a bind is configured but no questionnaire or table uses it.

    Likely a typo or a stale config. Soft warning rather than fatal because
    a researcher may be mid-setup, or may use the bind programmatically in a
    custom blueprint's hand-written SQLAlchemy model (which won't appear in
    ``app.questionnaires`` / ``app.tables``).
    """
    configured = set(app.config.get("SQLALCHEMY_BINDS", {}) or {})
    if not configured:
        return
    used = {getattr(q, 'bind_key', None) for q in app.questionnaires.values()}
    used |= {getattr(t, 'bind_key', None) for t in app.tables.values()}
    used.discard(None)
    for unused in sorted(configured - used):
        app.setup_diagnostics.add(
            "warning", "bind",
            f"SQLALCHEMY_BINDS entry {unused!r} is configured but no "
            f"questionnaire or table references it.",
            suggestion=(
                f"Set `database: \"{unused}\"` on a JSON file, or remove "
                f"the bind from your config."
            ),
            source=f"SQLALCHEMY_BINDS.{unused}",
        )


# Sample size in the orphan warning. Enough that a researcher can spot the
# pattern (e.g. all orphans clustered in a contiguous ID range from an old
# study) without flooding the log when something has gone catastrophically
# wrong and every row is an orphan.
_ORPHAN_SAMPLE_LIMIT = 10


def warn_about_orphan_participants(app) -> None:
    """Detect rows on a non-default bind whose ``participantID`` value
    doesn't exist in the default-bind ``participant`` table.

    SQLAlchemy can't enforce a FK across engines, so a partial restore
    (researcher copies a stale ``main.db`` over the current one, or deletes
    only one bind file out of band) silently leaves orphan PII rows that
    will be silently reattributed when ``participantID`` values get reused
    by new participants. This check catches that state at startup so the
    researcher sees it before the next signup makes the privacy leak
    permanent.

    The check is a soft warning, not a fatal error: legitimate cases exist
    (e.g. importing PII from a prior wave while the new study's
    participants haven't signed up yet). The framework can't tell the
    difference, so it logs and lets the researcher decide.
    """
    from sqlalchemy import select, inspect as sa_inspect
    from .globals import db

    configured = app.config.get("SQLALCHEMY_BINDS", {}) or {}
    if not configured:
        return

    # Pull the full set of known participantIDs once. On the default bind
    # this is a single indexed query against the primary key.
    default_engine = db.engine
    default_inspector = sa_inspect(default_engine)
    if 'participant' not in default_inspector.get_table_names():
        # Fresh project, nothing to check against yet.
        return
    participant_tbl = db.metadatas[None].tables.get('participant')
    if participant_tbl is None:
        return
    with default_engine.connect() as conn:
        known_pids = {
            row[0]
            for row in conn.execute(select(participant_tbl.c.participantID))
        }

    for bind_key in configured:
        bind_md = db.metadatas.get(bind_key)
        if bind_md is None:
            continue
        try:
            bind_engine = db.engines[bind_key]
        except KeyError:
            continue
        bind_inspector = sa_inspect(bind_engine)
        existing_tables = set(bind_inspector.get_table_names())

        for table_name, table in bind_md.tables.items():
            if table_name not in existing_tables:
                # Schema declared but DB hasn't been created yet — nothing
                # to check.
                continue
            pid_col = table.c.get('participantID')
            if pid_col is None:
                # Not every cross-bind table is participant-keyed (a
                # blueprint might use the bind for a stimulus catalog, say).
                continue

            with bind_engine.connect() as conn:
                bind_pids = {
                    row[0]
                    for row in conn.execute(
                        select(pid_col).distinct().where(pid_col.isnot(None))
                    )
                }

            orphans = sorted(bind_pids - known_pids)
            if not orphans:
                continue

            shown = orphans[:_ORPHAN_SAMPLE_LIMIT]
            more = len(orphans) - len(shown)
            sample = ", ".join(str(p) for p in shown)
            if more > 0:
                sample += f", ... (+{more} more)"
            app.setup_diagnostics.add(
                "warning", "bind",
                f"Table {table_name!r} on bind {bind_key!r} has "
                f"{len(orphans)} row(s) referencing participantID values "
                f"that don't exist in the default-bind participant table: "
                f"{sample}. These are orphans — most likely from a partial "
                f"DB restore or out-of-band editing.",
                suggestion=(
                    "A new participant assigned a reused ID will silently "
                    "inherit the orphan row's data. Rotate or delete the "
                    "orphans before letting new participants sign up."
                ),
                source=f"{bind_key}.{table_name}",
            )


def warn_undecorated_pages(app) -> None:
    """Emit a warning for any PAGE_LIST entry whose route is missing the
    ``@verify_correct_page`` decorator. The decorator enforces page-list
    ordering — without it, participants can land on a page out of order
    and the framework can't redirect them back. Called once at startup."""
    adapter = app.url_map.bind('localhost')
    for page in app.page_list.flat_page_list(condition=0):
        path = page.get('path', '')
        if not path or path in _PAGES_DECORATOR_NOT_REQUIRED:
            continue
        try:
            endpoint, _ = adapter.match('/' + path)
        except Exception:
            app.setup_diagnostics.add(
                "warning", "route",
                f"PAGE_LIST entry {path!r} doesn't match any registered route.",
                suggestion=(
                    "Participants navigating to this page will see a 404. "
                    "Add a matching route in a blueprint, or fix the path "
                    "in PAGE_LIST."
                ),
                source=path,
            )
            continue

        view_func = app.view_functions.get(endpoint)
        if view_func is None:
            continue
        if getattr(view_func, '_bofs_suppress_activity_polling', False):
            continue  # Researcher is managing this route manually.
        if not getattr(view_func, '_bofs_verify_correct_page', False):
            app.setup_diagnostics.add(
                "warning", "route",
                f"PAGE_LIST entry {path!r} maps to view {endpoint} which is "
                f"missing @verify_correct_page.",
                suggestion=(
                    "The decorator enforces page-list ordering and "
                    "bootstraps session state; without it, participants "
                    "can navigate to this page out of order."
                ),
                source=path,
            )
