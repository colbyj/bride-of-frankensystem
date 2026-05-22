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
            print(
                "NOTE: SECRET_KEY in your config has been migrated into the project database. "
                "BOFS now manages SECRET_KEY automatically — you can safely remove the line "
                "from your .toml config file."
            )
        else:
            new_key = secrets.token_hex(32)
            app.db.session.add(app.db.AppMeta(key='secret_key', value=new_key))
            app.db.session.commit()
            app.config['SECRET_KEY'] = new_key
        return

    # Stored value already exists — it is the source of truth.
    if config_key and config_key != stored.value:
        print(
            "NOTE: SECRET_KEY is set in your config but BOFS is using the value persisted "
            "in the project database. The config line is ignored and can be removed."
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

    from .validation import RESERVED_EXPRESSION_NAMES, ValidationResult
    if filename in RESERVED_EXPRESSION_NAMES:
        app.validation_errors.append(ValidationResult(
            "error", filename + ".json",
            f"Table filename '{filename}' conflicts with a reserved "
            f"expression name. Tables and questionnaires cannot be named "
            f"any of: {', '.join(sorted(RESERVED_EXPRESSION_NAMES))}.",
            f"Rename '{filename}.json' to something else."
        ))
        print(app.validation_errors[-1])
        return None

    print(f"Loaded table: {directory}/{filename}.json")
    table = JSONTable(directory, filename)

    if table.json_data:
        from .validation import validate_table
        errors = validate_table(table.json_data, filename)
        fatal = [e for e in errors if e.severity == "error"]
        warnings = [e for e in errors if e.severity == "warning"]
        for w in warnings:
            print(w)
        app.validation_errors.extend(warnings)
        if fatal:
            app.validation_errors.extend(fatal)
            for err in fatal:
                print(err)
            print(f"  Skipping table '{filename}' due to "
                  f"{len(fatal)} error(s).")
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
    from .validation import validate_questionnaire, RESERVED_EXPRESSION_NAMES, ValidationResult

    if "questionnaire_" + filename in app.db.metadata.tables:
        return None

    if filename in app.questionnaires:
        return None

    if filename in RESERVED_EXPRESSION_NAMES:
        app.validation_errors.append(ValidationResult(
            "error", filename + ".json",
            f"Questionnaire filename '{filename}' conflicts with a "
            f"reserved expression name. Questionnaires and tables cannot "
            f"be named any of: "
            f"{', '.join(sorted(RESERVED_EXPRESSION_NAMES))}.",
            f"Rename '{filename}.json' to something else."
        ))
        print(app.validation_errors[-1])
        return None

    # Try to load the JSON file
    try:
        questionnaire = JSONQuestionnaire(directory, filename, add_to_db)
    except (SyntaxError, FileNotFoundError, IOError) as e:
        app.validation_errors.append(ValidationResult(
            "error", filename, str(e),
            "Check that the file exists and contains valid JSON syntax."
        ))
        print(f"  ERROR loading questionnaire '{filename}': {e}")
        return None

    # Validate the questionnaire JSON before creating the DB class
    errors = validate_questionnaire(questionnaire.json_data, filename, valid_question_types)
    fatal_errors = [e for e in errors if e.severity == "error"]
    warnings = [e for e in errors if e.severity == "warning"]

    for w in warnings:
        print(w)
    app.validation_errors.extend(warnings)

    if fatal_errors:
        app.validation_errors.extend(fatal_errors)
        for err in fatal_errors:
            print(err)
        print(f"  Skipping questionnaire '{filename}' due to {len(fatal_errors)} error(s).")
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
    page_list_errors = validate_page_list_references(
        app.config['PAGE_LIST'], app.questionnaire_paths
    )
    if page_list_errors:
        app.validation_errors.extend(page_list_errors)
        for err in page_list_errors:
            print(err)


def get_questionnaire_path(app, questionnaire_to_find: str) -> Union[str, None]:
    for path in app.questionnaire_paths:
        for questionnaire_filename in app.questionnaire_paths[path]:
            if questionnaire_to_find == questionnaire_filename:
                return str(os.path.join(path, questionnaire_filename + ".json"))
    return None


# ---------------------------------------------------------------------------
# Startup warnings
# ---------------------------------------------------------------------------

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
            app.logger.warning(
                "PAGE_LIST entry %r doesn't match any registered route. "
                "Participants navigating to this page will see a 404.",
                path,
            )
            continue

        view_func = app.view_functions.get(endpoint)
        if view_func is None:
            continue
        if getattr(view_func, '_bofs_suppress_activity_polling', False):
            continue  # Researcher is managing this route manually.
        if not getattr(view_func, '_bofs_verify_correct_page', False):
            app.logger.warning(
                "PAGE_LIST entry %r maps to view %s which is missing "
                "@verify_correct_page. The decorator enforces page-list "
                "ordering and bootstraps session state; without it, "
                "participants can navigate to this page out of order.",
                path, endpoint,
            )
