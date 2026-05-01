import os
import re
import secrets
import sys
from .BOFSFlask import BOFSFlask
from .admin.util import check_and_add_column, make_columns_nullable

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


def _resolve_secret_key(app) -> None:
    """
    Load SECRET_KEY from the app_meta table, or generate and persist one.

    Honors a SECRET_KEY supplied in the project config (legacy behavior): the
    value is seeded into app_meta on first run with a one-time notice. On
    subsequent runs the database value is the source of truth — the config
    line is ignored, and a notice is printed reminding the researcher to
    remove it.
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


def create_app(path, config_name, debug=False, reloader_off=False):
    os.chdir(path)  # Set the current working directory to the specified path
    sys.path.append(path)  # Ensure BOFS can find the blueprints properly

    app = BOFSFlask(__name__,
                    config_name=config_name,
                    root_path=path,
                    run_with_debugging=debug,
                    run_with_reloader_off=reloader_off)

    if 'USE_ADMIN' not in app.config or app.config['USE_ADMIN'] is True:
        app.load_blueprint('BOFS.admin', 'admin')

    # Set defaults for some config options
    if 'USE_BREADCRUMBS' not in app.config:
        app.config['USE_BREADCRUMBS'] = True

    header_color = app.config.get('HEADER_COLOR')
    if header_color is not None:
        if isinstance(header_color, str) and _HEADER_COLOR_RE.match(header_color):
            app.config['HEADER_COLOR'] = header_color.strip()
        else:
            print(
                f"WARNING: HEADER_COLOR={header_color!r} is not a valid CSS color "
                f"(expected hex like '#8CB737', a named color, or rgb()/rgba()/hsl()/hsla()). "
                f"Falling back to the default header color."
            )
            app.config['HEADER_COLOR'] = None

    if 'USE_LOGO' not in app.config:
        app.config['USE_LOGO'] = True

    if 'LOG_GRID_CLICKS' in app.config and 'LOG_QUESTIONNAIRE_INTERACTIONS' not in app.config:
        app.config['LOG_QUESTIONNAIRE_INTERACTIONS'] = app.config['LOG_GRID_CLICKS']
        app.logger.warning(
            "Config key LOG_GRID_CLICKS is deprecated; rename to "
            "LOG_QUESTIONNAIRE_INTERACTIONS in your config.toml."
        )

    if 'LOG_QUESTIONNAIRE_INTERACTIONS' not in app.config:
        app.config['LOG_QUESTIONNAIRE_INTERACTIONS'] = False

    if 'ADDITIONAL_ADMIN_PAGES' not in app.config:
        app.config['ADDITIONAL_ADMIN_PAGES'] = []

    if 'EXPORT' not in app.config:
        app.config['EXPORT'] = []

    if 'ALLOW_RETAKES' not in app.config:
        app.config['ALLOW_RETAKES'] = False

    if 'RETRIEVE_SESSIONS' not in app.config:
        app.config['RETRIEVE_SESSIONS'] = True

    if 'EXTERNAL_ID_LABEL' not in app.config:
        app.config['EXTERNAL_ID_LABEL'] = "Mechanical Turk Worker ID"

    if 'EXTERNAL_ID_PROMPT' not in app.config:
        app.config['EXTERNAL_ID_PROMPT'] = "Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."

    if 'GENERATE_COMPLETION_CODE' not in app.config:
        app.config['GENERATE_COMPLETION_CODE'] = True

    if 'STATIC_COMPLETION_CODE' not in app.config:
        app.config['STATIC_COMPLETION_CODE'] = None

    if 'COMPLETION_CODE_MESSAGE' not in app.config:
        app.config['COMPLETION_CODE_MESSAGE'] = "Please copy and paste this code into the MTurk form:"

    if 'OUTGOING_URL' not in app.config:
        app.config['OUTGOING_URL'] = None

    if 'ABANDONED_MINUTES' not in app.config:
        app.config['ABANDONED_MINUTES'] = 5

    if 'COUNTS_INCLUDE_ABANDONED' not in app.config:
        app.config['COUNTS_INCLUDE_ABANDONED'] = False

    if 'CONDITIONS' not in app.config:
        app.config['CONDITIONS'] = []

    if 'CONDITIONS_FROM_CSV' not in app.config:
        app.config['CONDITIONS_FROM_CSV'] = None

    if 'CONDITIONS_FROM_DB' not in app.config:
        app.config['CONDITIONS_FROM_DB'] = None

    # Validate and prime the condition-lookup service. Either source raises
    # ConditionLookupConfigError on misconfiguration, which we let propagate
    # so the app fails fast on startup with a clear message.
    from .services.condition_lookup import ConditionLookupService
    ConditionLookupService.init_app(app)

    # Flask defaults APPLICATION_ROOT to '/', but that causes issues with URL concatenation
    # (e.g., "/" + "/" + "consent" = "//consent" which is interpreted as a protocol-relative URL)
    if 'APPLICATION_ROOT' not in app.config or app.config['APPLICATION_ROOT'] == '/':
        app.config['APPLICATION_ROOT'] = ''

    if 'BRUTE_FORCE_PROTECTION' not in app.config:
        app.config['BRUTE_FORCE_PROTECTION'] = True

    if 'BRUTE_FORCE_AUTO_TRUST_ADMIN' not in app.config:
        app.config['BRUTE_FORCE_AUTO_TRUST_ADMIN'] = True

    if 'BRUTE_FORCE_MAX_ATTEMPTS' not in app.config:
        app.config['BRUTE_FORCE_MAX_ATTEMPTS'] = 5

    if 'BRUTE_FORCE_WINDOW_MINUTES' not in app.config:
        app.config['BRUTE_FORCE_WINDOW_MINUTES'] = 15

    if 'BRUTE_FORCE_BAN_SCHEDULE' not in app.config:
        app.config['BRUTE_FORCE_BAN_SCHEDULE'] = [1, 2, 5, 15, 60, 360, 1440, 10080]

    if 'BRUTE_FORCE_PROBE_URLS' not in app.config:
        app.config['BRUTE_FORCE_PROBE_URLS'] = [
            "/.env",
            "/.git",
            "/.aws",
            "/wp-admin",
            "/wp-login.php",
            "/wp-includes",
            "/wp-content",
            "/xmlrpc.php",
            "/phpmyadmin",
            "/phpMyAdmin",
            "/administrator",
            "/admin.php",
            "/server-status",
            "/actuator",
            "/vendor/phpunit",
            "/cgi-bin",
            "/.DS_Store",
            "/.htaccess",
            "/.svn",
        ]

    if 'BRUTE_FORCE_HOSTILE_UA_PATTERNS' not in app.config:
        app.config['BRUTE_FORCE_HOSTILE_UA_PATTERNS'] = [
            "sqlmap", "nikto", "nmap", "dirbuster", "gobuster",
            "masscan", "WPScan", "acunetix", "nessus",
        ]

    if 'SESSION_BIND_TO_IP_PARTICIPANT' not in app.config:
        app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = True

    if 'TRUSTED_IPS' not in app.config:
        app.config['TRUSTED_IPS'] = []

    if 'BEHIND_REVERSE_PROXY' not in app.config:
        app.config['BEHIND_REVERSE_PROXY'] = False

    if app.config['BEHIND_REVERSE_PROXY']:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    for current_path in os.listdir(path):
        if current_path in ["static", "templates"]:  # We're inside a blueprint. Unlikely that there is another one here...
            continue

        considered_path = os.path.join(path, current_path)

        if os.path.isdir(considered_path) and not current_path.startswith("."):  # We should try this path.
            found_views = False

            for subpath in os.listdir(considered_path):
                if subpath == "views.py":
                    app.load_blueprint(current_path, current_path, False)
                    found_views = True
                if subpath == "models.py":
                    app.load_models(current_path)

            if not found_views:  # If no views, then create a blank blueprint, so we can still search the templates folder, etc.
                app.load_empty_blueprint(current_path)

    app.load_blueprint('BOFS.default', 'default')

    with app.app_context():
        if not app.questionnaire_list_is_safe():
            print("Error! The same questionnaire was specified twice. Please add a tag to your questionnaire if this "
                  "was intentional.")
            return

        app.load_questionnaires()
        app.load_tables()

        from .validation import validate_page_show_if_table_refs
        table_ref_warnings = validate_page_show_if_table_refs(
            app.page_list.page_list, app.tables
        )
        if table_ref_warnings:
            app.validation_errors.extend(table_ref_warnings)
            for w in table_ref_warnings:
                print(w)

        # Make orphaned DB columns nullable (before db.create_all so the model matches)
        for q_key in app.questionnaires:
            q = app.questionnaires[q_key]
            orphaned = getattr(q, '_orphaned_columns', None) or []
            if orphaned:
                orphaned_names = [col['name'] for col in orphaned]
                make_columns_nullable(q.db_class.__tablename__, orphaned_names)

        # Print validation summary (JSON-level errors only; schema warnings come later)
        fatal_errors = [e for e in app.validation_errors if e.severity == "error"]
        warnings = [e for e in app.validation_errors if e.severity == "warning"]
        if fatal_errors:
            print(f"\n{'='*60}")
            print(f"QUESTIONNAIRE VALIDATION: {len(fatal_errors)} error(s), {len(warnings)} warning(s)")
            print(f"The experiment will NOT be accessible until these errors are fixed.")
            print(f"Open the app in a browser to see detailed error descriptions.")
            print(f"{'='*60}\n")

        app.db.create_all()

        # SECRET_KEY is now persisted in the app_meta table rather than the
        # project's TOML config. This avoids accidental commits of secrets and
        # ensures distinct projects on the same host don't end up sharing a key.
        _resolve_secret_key(app)

        # Check to see if all the columns are there
        # These are columns added to newer versions of BOFS
        check_and_add_column('participant', 'excludeFromCount', 'BOOLEAN', 0)
        check_and_add_column('participant', 'notes', 'TEXT', '')

        if check_and_add_column('participant', 'isCrawler', 'BOOLEAN', 0):
            # If this column wasn't in there, then also check all prior participants' useragent.
            participants = app.db.session.query(app.db.Participant).all()
            for participant in participants:
                participant.check_useragent_for_crawler()
            app.db.session.commit()
            print("Checking participants for web scrapers.")

        # Now user-defined questionnaires (only those that passed validation)
        # New columns are added as nullable — existing rows will have NULL
        for q_key in app.questionnaires:
            q = app.questionnaires[q_key]
            q_fields = q.fetch_fields()
            table_name = q.db_class.__tablename__

            for field in q_fields:
                if check_and_add_column(table_name, field.id, field.get_type_ddl()):
                    print(f"Added new column to {table_name}: {field.id}")

        for t_key in app.tables:
            t = app.tables[t_key]
            columns = t.get_columns()
            table_name = t.db_class.__tablename__

            for column in columns:
                if check_and_add_column(table_name, column.name, column.get_type_ddl(), column.default):
                    print(f"Added new column to {t_key}: {column.name}")

        # Check for DB-vs-JSON schema mismatches and generate warnings
        from .validation import validate_db_schema
        for q_key in app.questionnaires:
            q = app.questionnaires[q_key]
            schema_warnings = validate_db_schema(q, q_key)
            if schema_warnings:
                app.validation_errors.extend(schema_warnings)
                for w in schema_warnings:
                    print(w)

        # Warn about PAGE_LIST routes missing @verify_correct_page (which
        # enforces ordering and bootstraps session state).
        app.warn_undecorated_pages()

    return app
