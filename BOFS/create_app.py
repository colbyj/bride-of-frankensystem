import os
import sys
from . import startup
from .BOFSFlask import BOFSFlask
from .admin.util import check_and_add_column, check_and_rename_column, make_columns_nullable
from .validation import is_valid_header_color


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
        if is_valid_header_color(header_color):
            app.config['HEADER_COLOR'] = header_color.strip()
        else:
            app.setup_diagnostics.add(
                "warning", "config",
                f"HEADER_COLOR={header_color!r} is not a valid CSS color. "
                f"Falling back to the default header color.",
                suggestion=(
                    "Use a hex value like '#8CB737', a named color, or "
                    "rgb()/rgba()/hsl()/hsla() functional notation."
                ),
                source="HEADER_COLOR",
            )
            app.config['HEADER_COLOR'] = None

    if 'USE_LOGO' not in app.config:
        app.config['USE_LOGO'] = True

    if 'LOG_GRID_CLICKS' in app.config and 'LOG_QUESTIONNAIRE_INTERACTIONS' not in app.config:
        app.config['LOG_QUESTIONNAIRE_INTERACTIONS'] = app.config['LOG_GRID_CLICKS']
        app.setup_diagnostics.add(
            "warning", "config",
            "Config key LOG_GRID_CLICKS is deprecated.",
            suggestion="Rename LOG_GRID_CLICKS to LOG_QUESTIONNAIRE_INTERACTIONS in your config.toml.",
            source="LOG_GRID_CLICKS",
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
        # If a user tries to access these URLs, they are likely a bad actor.
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
        # For security purposes, we bind the session to a particular IP, so
        # that the session can't be hijacked so easily.
        app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = True

    if 'SESSION_COOKIE_SAMESITE' not in app.config:
        # Lax keeps cookies on top-level navigations (so the MTurk/Prolific
        # post-completion redirect still carries them) but blocks cross-site
        # POSTs from arbitrary origins to participant routes.
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    if 'MAX_CONTENT_LENGTH' not in app.config:
        # Cap request bodies so a single hostile participant can't tie up a
        # waitress thread with an unbounded POST. 8 MB easily covers
        # questionnaire submissions and base64 image uploads.
        app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

    if 'TRUSTED_IPS' not in app.config:
        # Can indicate IPs to exclude from the admin login brute-force check.
        app.config['TRUSTED_IPS'] = []

    if 'BEHIND_REVERSE_PROXY' not in app.config:
        # If behind a reverse proxy, need to look for specific HTTP headers that the proxy adds to requests.
        # This lets us know a user's IP address, for example, instead of just seeing the proxy's IP address.
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
            app.setup_diagnostics.add(
                "error", "page_list",
                "The same questionnaire was specified twice in PAGE_LIST.",
                suggestion=(
                    "Add a `tag` to one of the entries if the duplication "
                    "is intentional, so the two submissions can be stored "
                    "and retrieved independently."
                ),
            )
            # Continue construction so the error surfaces on the
            # fatal-error page instead of crashing the app silently.

        app.load_questionnaires()
        app.load_tables()

        if app.config.get('USE_BREADCRUMBS', True) and app.page_list.has_branching():
            app.setup_diagnostics.add(
                "warning", "page_list",
                "USE_BREADCRUMBS is enabled and PAGE_LIST contains "
                "conditional_routing or show_if predicates. The breadcrumb "
                "only shows pages BOFS knows the participant will visit, "
                "so it will grow as participants answer gating questions.",
                suggestion=(
                    "If a growing breadcrumb is undesirable, set "
                    "USE_BREADCRUMBS = false in your config."
                ),
                source="USE_BREADCRUMBS",
            )

        from .validation import validate_page_show_if_table_refs
        for w in validate_page_show_if_table_refs(app.page_list.page_list, app.tables):
            app.setup_diagnostics.append(w)

        # Make orphaned DB columns nullable (before db.create_all so the model matches)
        for q_key in app.questionnaires:
            q = app.questionnaires[q_key]
            orphaned = getattr(q, '_orphaned_columns', None) or []
            if orphaned:
                orphaned_names = [col['name'] for col in orphaned]
                make_columns_nullable(q.db_class.__tablename__, orphaned_names,
                                      bind_key=getattr(q, 'bind_key', None))

        # Print a startup summary banner so the researcher sees totals in
        # the terminal even when running headless. Individual diagnostics
        # are already in the collector (and have been mirrored to the
        # logger). The full structured view is on the landing-page
        # interstitial and the fatal-error page.
        fatal_errors = app.setup_diagnostics.by_severity("error")
        warnings = app.setup_diagnostics.by_severity("warning")
        if fatal_errors:
            print(f"\n{'='*60}")
            print(f"BOFS SETUP: {len(fatal_errors)} error(s), {len(warnings)} warning(s)")
            print(f"The experiment will NOT be accessible until these errors are fixed.")
            print(f"Open the app in a browser to see detailed error descriptions.")
            print(f"{'='*60}\n")
        elif warnings:
            print(f"\nBOFS setup: {len(warnings)} warning(s). Open the app to view details.\n")

        # Flask-SQLAlchemy iterates every configured engine (default plus
        # SQLALCHEMY_BINDS) and emits each model against the engine matching
        # its __bind_key__. Cross-bind questionnaires/tables land on their
        # bound engine; default-bind models stay on the default engine.
        app.db.create_all()

        # SECRET_KEY is now persisted in the app_meta table rather than the
        # project's TOML config. This avoids accidental commits of secrets and
        # ensures distinct projects on the same host don't end up sharing a key.
        startup.resolve_secret_key(app)

        # Check to see if all the columns are there
        # These are columns added to newer versions of BOFS
        # Rename `mTurkID` -> `external_id` on existing databases. The ORM
        # uses `externalID` (Python) / `external_id` (DB) with a `mTurkID`
        # synonym; on a fresh DB, create_all() above already created
        # `external_id` and these calls are no-ops.
        check_and_rename_column('participant', 'mTurkID', 'external_id')
        check_and_rename_column('session_store', 'mTurkID', 'external_id')

        check_and_add_column('participant', 'excludeFromCount', 'BOOLEAN', 0)
        check_and_add_column('participant', 'notes', 'TEXT', '')

        # Recruitment source; nullable for back-compat with existing rows.
        # The matching index keeps `source == "..."` expression filters and
        # admin source-filter queries cheap on large tables.
        if check_and_add_column('participant', 'source', 'VARCHAR', None):
            with app.db.engine.begin() as conn:
                conn.execute(app.db.DDL(
                    "CREATE INDEX IF NOT EXISTS ix_participant_source "
                    "ON participant (source)"
                ))

        # Why the session ended. NULL for participants who abandoned mid-study.
        # Indexed because admin dashboards group/filter by it.
        if check_and_add_column('participant', 'end_reason', 'VARCHAR', None):
            with app.db.engine.begin() as conn:
                conn.execute(app.db.DDL(
                    "CREATE INDEX IF NOT EXISTS ix_participant_end_reason "
                    "ON participant (end_reason)"
                ))

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
            bind_key = getattr(q, 'bind_key', None)

            for field in q_fields:
                if check_and_add_column(table_name, field.id, field.get_type_ddl(),
                                        bind_key=bind_key):
                    print(f"Added new column to {table_name}: {field.id}")

        for t_key in app.tables:
            t = app.tables[t_key]
            columns = t.get_columns()
            table_name = t.db_class.__tablename__
            bind_key = getattr(t, 'bind_key', None)

            for column in columns:
                if check_and_add_column(table_name, column.name, column.get_type_ddl(),
                                        column.default, bind_key=bind_key):
                    print(f"Added new column to {t_key}: {column.name}")

        # Check for DB-vs-JSON schema mismatches and generate warnings
        from .validation import validate_db_schema
        for q_key in app.questionnaires:
            q = app.questionnaires[q_key]
            for w in validate_db_schema(q, q_key):
                app.setup_diagnostics.append(w, category="schema")

        # Warn about PAGE_LIST routes missing @verify_correct_page (which
        # enforces ordering and bootstraps session state).
        app.warn_undecorated_pages()

        # Warn about binds that aren't referenced by any questionnaire/table
        # (likely typo). Also walk every cross-bind table with a
        # participantID column and surface rows whose participantID isn't
        # in the default-bind participant table (orphan PII from a
        # partial restore or out-of-band DB editing).
        app.warn_about_unused_binds()
        app.warn_about_orphan_participants()

    return app
