from datetime import datetime
from crawlerdetect import CrawlerDetect
import jinja2
import json
import toml
import os
import random
from typing import Union
from flask import Flask, send_from_directory, Response, Blueprint, url_for, render_template, session
from flask_sqlalchemy import SQLAlchemy
from flask_compress import Compress
from markupsafe import Markup
from BOFS import util
from .BOFSSession import BOFSSessionInterface
from .JSONQuestionnaire import JSONQuestionnaire
from .JSONTable import JSONTable
from .PageList import PageList


class BOFSFlask(Flask):
    def __init__(self, import_name, config_name, root_path=None, run_with_reloader_off=False, run_with_debugging=False):
        super(BOFSFlask, self).__init__(import_name)
        self.run_with_reloader_off = run_with_reloader_off
        self.run_with_debugging = run_with_debugging

        if root_path:
            self.root_path = root_path

        self.config = self.make_config()
        self.load_config(config_name)
        self.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        # Validate required config values
        if 'PAGE_LIST' not in self.config:
            raise ValueError(
                f"Configuration file '{config_name}' is missing required 'PAGE_LIST' setting.\n"
                f"Please add a PAGE_LIST to define your experiment's page flow."
            )

        self.page_list = PageList(self.config['PAGE_LIST'])

        self.bofs_path = os.path.dirname(__file__)  # Get the path to where the BOFS files (like this file) are
        self.instance_path = os.path.dirname(os.path.abspath(config_name))  # Get the current working path.

        self.db = SQLAlchemy(self)

        self.questionnaires : dict[str, JSONQuestionnaire] = {}
        """A generated list of user-defined questionnaires, as found in the config file."""

        self.tables : dict[str, JSONTable] = {}
        """A generated list of user-defined tables, specifically those found in the tables directories."""

        self.compress = Compress(self)

        self.session_interface = BOFSSessionInterface()
        """Used to store Flask session in the database."""

        self.crawler_detect = CrawlerDetect()
        """Used to detect when search engines, etc. are viewing the project."""

        self.validation_errors: list = []
        """Questionnaire validation errors collected during startup."""

        self.add_url_rule("/BOFS_static/<path:filename>", endpoint="BOFS_static", view_func=self.route_BOFS_static)
        self.add_url_rule("/consent.html", endpoint="consent_html", view_func=self.route_consent)
        self.register_error_handler(404, self.page_not_found)

        if not self.run_with_debugging:
            self.register_error_handler(500, self.internal_error)

        default_templates_path = os.path.join(self.bofs_path, "templates")
        project_templates_path = os.path.join(self.instance_path, 'templates')

        # Allows developers of BOFS deployments to override BOFS templates
        self.my_loader = jinja2.ChoiceLoader([
            self.jinja_loader,
            jinja2.FileSystemLoader(default_templates_path),
            jinja2.FileSystemLoader(project_templates_path),
        ])

        self.jinja_loader = self.my_loader

        self.jinja_env.add_extension("jinja2.ext.do")

        # allows flat_page_list variable to be accessible from all templates
        self.template_context_processors[None].append(self.inject_jinja_vars)
        self.before_request_funcs.setdefault(None, []).append(self.before_request_)
        self.after_request_funcs.setdefault(None, []).append(self.after_request_)

        self.questionnaire_paths = {}
        self.table_paths = {}

    # Overriding Flask.run so production mode uses waitress instead of Flask's dev server.
    def run(self, host=None, port=None, **options) -> None:
        actual_port = port if port is not None else 5000
        actual_host = host if not host is None else '127.0.0.1'

        print(f"Listening on http://{actual_host}:{actual_port}")
        if actual_host != '127.0.0.1':
            print(f"Preview locally at http://127.0.0.1:{actual_port}")

        if self.run_with_debugging:
            print('\033[91m' + '\033[1m')  # Start red text
            print("!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!")
            print(" Debugging mode is enabled. ")
            print(" Do not use this as a production web server. ")
            print("!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!")
            print('\033[0m')  # End the red

            if not self.run_with_reloader_off:
                print('Auto-reloading of project when changes are detected is turned ON.')

            super(BOFSFlask, self).run(host, port, debug=True, use_reloader=not self.run_with_reloader_off, **options)
        else:
            self.waitress_run(host=host, port=port)

    def waitress_run(self, host=None, port=None) -> None:
        from waitress import serve

        # Default of 4 is a bit low for a standalone server when static assets are being
        # served (as they are in our case). Configurable via WAITRESS_THREADS.
        threads = self.config.get('WAITRESS_THREADS', 16)

        try:
            serve(self, host=host, port=port, threads=threads)
        except KeyboardInterrupt:
            pass

    def load_config(self, filename, silent=False) -> None:
        # Check if the file exists first
        if not os.path.exists(filename):
            raise FileNotFoundError(
                f"Configuration file not found: '{filename}'\n"
                f"Make sure the file exists and you're running BOFS from the correct directory."
            )

        if filename.endswith(".cfg"):
            self.config.from_pyfile(filename, silent=silent)
        elif filename.endswith(".toml"):
            try:
                self.config.from_file(filename, load=toml.load)
            except toml.TomlDecodeError as e:
                raise ValueError(f"Invalid TOML syntax in '{filename}': {e}")
        elif filename.endswith(".json"):
            try:
                self.config.from_file(filename, load=json.load)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON syntax in '{filename}': {e}")
        else:
            raise ValueError(
                f"Unsupported configuration file format: '{filename}'\n"
                f"BOFS supports .toml, .json, and .cfg configuration files."
            )

    def load_empty_blueprint(self, blueprint_path):
        print("Creating empty blueprint: %s" % blueprint_path)

        blueprint_var = Blueprint(blueprint_path, blueprint_path,
                                  static_url_path='/' + blueprint_path,
                                  template_folder=os.path.join(blueprint_path, 'templates'),
                                  static_folder=os.path.join(blueprint_path, 'static'))

        self.register_blueprint(blueprint_var)
        #self.my_loader.loaders.

    def load_blueprint(self, blueprint_path, blueprint_name=None, try_to_load_models=True) -> None:
        print("Loaded blueprint: %s" % blueprint_path)

        if blueprint_name is None:
            blueprint_name = blueprint_path

        blueprint = __import__(blueprint_path + ".views", fromlist=["views"])
        blueprint_var = getattr(blueprint, blueprint_name)
        self.register_blueprint(blueprint_var)

        if 'DEFAULT_FIELD_WIDTH' not in self.config:
            self.config['DEFAULT_FIELD_WIDTH'] = 400

        if 'ADDITIONAL_ADMIN_PAGES' not in self.config:
            self.config['ADDITIONAL_ADMIN_PAGES'] = []

        if hasattr(blueprint, 'ADDITIONAL_ADMIN_PAGES'):
            self.config['ADDITIONAL_ADMIN_PAGES'].append(blueprint.ADDITIONAL_ADMIN_PAGES)

        if 'EXPORT' not in self.config:
            self.config['EXPORT'] = []

        if hasattr(blueprint, 'EXPORT'):
            self.config['EXPORT'].extend(blueprint.EXPORT)

        if try_to_load_models:  # Try to load the models too.
            self.load_models(blueprint_path)

    def load_models(self, blueprint_path) -> None:
        try:
            module = __import__(blueprint_path + ".models", fromlist=["models"])
            create_function = getattr(module, "create")

            if create_function is None:
                print("Warning: %s.models does not contain a `create()` function! No models will be added.")
                return

            with self.app_context():
                my_classes = create_function(self.db)

            if hasattr(my_classes, '__iter__'):  # A list or tuple was returned
                for c in my_classes:
                    setattr(self.db, c.__name__, c)
                    if self.run_with_debugging:
                        print("%s: Loaded %s" % (blueprint_path, c))
            else:
                setattr(self.db, my_classes.__name__, my_classes)
                if self.run_with_debugging:
                    print("%s: Loaded %s" % (blueprint_path, my_classes))

            print("%s: `models.py` loaded!" % blueprint_path)
        except ImportError:
            print("%s: `models.py` not found. Add a `models.py` file to your blueprint folder use this feature." % blueprint_path)

    def load_table(self, directory: str, filename: str) -> Union[JSONTable, None]:
        if filename in self.db.metadata.tables:
            return None

        if filename in self.tables:
            return None

        from .validation import RESERVED_EXPRESSION_NAMES, ValidationResult
        if filename in RESERVED_EXPRESSION_NAMES:
            self.validation_errors.append(ValidationResult(
                "error", filename + ".json",
                f"Table filename '{filename}' conflicts with a reserved "
                f"expression name. Tables and questionnaires cannot be named "
                f"any of: {', '.join(sorted(RESERVED_EXPRESSION_NAMES))}.",
                f"Rename '{filename}.json' to something else."
            ))
            print(self.validation_errors[-1])
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
            self.validation_errors.extend(warnings)
            if fatal:
                self.validation_errors.extend(fatal)
                for err in fatal:
                    print(err)
                print(f"  Skipping table '{filename}' due to "
                      f"{len(fatal)} error(s).")
                return None

        table.create_db_class()
        exports_dict = table.create_exports_dict()

        if exports_dict is not None:
            self.config['EXPORT'] += exports_dict

        # Add the table as a database class, if it hasn't been added already.
        if not hasattr(self.db, table.db_class.__name__):
            setattr(self.db, table.db_class.__name__, table.db_class)

        self.tables[filename] = table
        return table

    def find_files_in_app_and_blueprints(self, folder_name: str, extension: str = ".json") -> dict[str, list[str]]:
        results: dict[str, list[str]] = {}

        app_path = os.path.join(self.root_path, folder_name)

        if os.path.exists(app_path):  # First find tables from /tables
            for file_name in os.listdir(app_path):
                if file_name.endswith(extension):
                    if app_path not in results:
                        results[app_path] = []

                    results[app_path].append(file_name.replace(extension, ""))

        # Next find tables from /<blueprint_name>/tables
        for blueprint_name in self.blueprints:
            blueprint_path = os.path.join(self.root_path,  blueprint_name, folder_name)

            if os.path.exists(blueprint_path):  # Does this blueprint have a directory we can look through?
                for q in os.listdir(blueprint_path):
                    if q.endswith(extension):
                        if blueprint_path not in results:
                            results[blueprint_path] = []

                        results[blueprint_path].append(q.replace(".json", ""))

        return results

    def load_tables(self) -> None:
        self.table_paths = self.find_files_in_app_and_blueprints("tables")

        for path in self.table_paths:
            for table_filename in self.table_paths[path]:
                self.load_table(path, table_filename)

    def load_questionnaire(self, directory:str , filename: str, add_to_db=False,
                           valid_question_types=None) -> Union[JSONQuestionnaire, None]:
        from .validation import validate_questionnaire, RESERVED_EXPRESSION_NAMES, ValidationResult

        if "questionnaire_" + filename in self.db.metadata.tables:
            return None

        if filename in self.questionnaires:
            return None

        if filename in RESERVED_EXPRESSION_NAMES:
            self.validation_errors.append(ValidationResult(
                "error", filename + ".json",
                f"Questionnaire filename '{filename}' conflicts with a "
                f"reserved expression name. Questionnaires and tables cannot "
                f"be named any of: "
                f"{', '.join(sorted(RESERVED_EXPRESSION_NAMES))}.",
                f"Rename '{filename}.json' to something else."
            ))
            print(self.validation_errors[-1])
            return None

        # Try to load the JSON file
        try:
            questionnaire = JSONQuestionnaire(directory, filename, add_to_db)
        except (SyntaxError, FileNotFoundError, IOError) as e:
            from .validation import ValidationResult
            self.validation_errors.append(ValidationResult(
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
        self.validation_errors.extend(warnings)

        if fatal_errors:
            self.validation_errors.extend(fatal_errors)
            for err in fatal_errors:
                print(err)
            print(f"  Skipping questionnaire '{filename}' due to {len(fatal_errors)} error(s).")
            return None

        # Validation passed — create the DB class
        print(f"Loaded questionnaire: {filename}, add_to_db={add_to_db}")
        questionnaire.create_db_class()

        if add_to_db:
            setattr(self.db, "Questionnaire" + questionnaire.db_class.__name__, questionnaire.db_class)

        self.questionnaires[filename] = questionnaire
        return questionnaire

    def questionnaire_list_is_safe(self) -> bool:
        """
        Checks to see if the questionnaire list has any duplicates.

        :return True if a duplicate was found, False otherwise.
        """
        questionnaires = self.page_list.get_questionnaire_list(include_tags=True)
        return len(set(questionnaires)) == len(questionnaires)

    def load_questionnaires(self) -> None:
        from .validation import validate_page_list_references, discover_question_types

        self.questionnaire_paths = self.find_files_in_app_and_blueprints("questionnaires")
        questionnaires_in_use = self.page_list.get_questionnaire_list()

        # Discover all valid question types (built-in + project + blueprints)
        valid_question_types = discover_question_types(self)

        for path in self.questionnaire_paths:
            for questionnaire_filename in self.questionnaire_paths[path]:
                add_to_db = questionnaire_filename in questionnaires_in_use
                self.load_questionnaire(path, questionnaire_filename, add_to_db, valid_question_types)

        # Check that all PAGE_LIST questionnaire references have matching files
        page_list_errors = validate_page_list_references(
            self.config['PAGE_LIST'], self.questionnaire_paths
        )
        if page_list_errors:
            self.validation_errors.extend(page_list_errors)
            for err in page_list_errors:
                print(err)

    def get_questionnaire_path(self, questionnaire_to_find) -> Union[str, None]:
        for path in self.questionnaire_paths:
            for questionnaire_filename in self.questionnaire_paths[path]:
                if questionnaire_to_find == questionnaire_filename:
                    return str(os.path.join(path, questionnaire_filename + ".json"))
        return None

    # Default routes...
    def route_BOFS_static(self, filename) -> Response:
        return send_from_directory(self.bofs_path + '/static', filename)

    def route_consent(self) -> Response:
        return send_from_directory(self.root_path, "consent.html")

    def page_not_found(self, e) -> tuple[str, int]:
        return render_template('error.html',
            title="Page Not Found",
            heading="File Not Found (404)",
            message="Could not load the requested page.",
            help_text=Markup(
                'If you are just starting out, please click <a href="/restart"><b>here</b></a> '
                "to reset your cookies for this page. If that doesn't work, please clear your "
                "cookies or switch web browsers."
            )
        ), 404

    @staticmethod
    def _strip_log_line(value) -> str:
        """Drop CR/LF so a value written to ``error.log`` can't forge new
        log lines. Used for fields that may carry user input bubbled up
        from request handlers (``error.description``, exception messages)."""
        if value is None:
            return ""
        return str(value).replace("\r", " ").replace("\n", " ")

    def internal_error(self, error):
        if not self.run_with_debugging:
            log_path = os.path.join(self.root_path, 'error.log')
            open_mode = 'a'
            if not os.path.exists(log_path):
                open_mode = 'w'

            with open(log_path, open_mode) as f:
                f.write(
                    f"{datetime.now()} - "
                    f"{self._strip_log_line(error.description)} - "
                    f"{self._strip_log_line(error.original_exception)}\n"
                )

        return render_template('error.html',
            title="Internal Server Error",
            heading="Internal Server Error (500)",
            message=str(error.description),
            # Markup.format auto-escapes the substituted exception text while
            # preserving the <pre> wrapper.
            help_text=Markup("<pre>{}</pre>").format(error.original_exception)
        ), 500

    def _current_participant(self):
        """Resolve the current participant from the Flask session, or
        ``None`` when there is no session, no participant assigned, or
        the row has been deleted. Used by :meth:`inject_jinja_vars` so
        templates can reference ``participant`` directly."""
        try:
            participant_id = session.get('participantID')
        except RuntimeError:
            return None
        if participant_id is None:
            return None
        participant_model = getattr(self.db, "Participant", None)
        if participant_model is None:
            return None
        return self.db.session.get(participant_model, participant_id)

    def inject_jinja_vars(self) -> dict:
        """
        Allows all templates to access several variables/methods used within BOFS.
        :return: a dictionary of variables/methods
        """
        style_url = url_for('BOFS_static', filename='style.css')

        # if there's another style.css at /static/style.css, then use that one instead.
        if os.path.exists(os.path.join(self.root_path, 'static', 'style.css')):
            style_url = url_for('static', filename='style.css')

        template_vars = dict(
            style_url=style_url,
            flat_page_list=self.page_list.flat_page_list(),
            debug=self.run_with_debugging,
            shuffle=random.shuffle,
            crumbs=util.create_breadcrumbs(),
            json_dumps=json.dumps,
            participant=self._current_participant(),
        )
        return template_vars

    def _too_many_requests_response(self, retry_seconds: int):
        """Render a 429 page with a ``Retry-After`` header."""
        body = render_template('error.html',
            title="Too Many Requests",
            heading="Too Many Requests (429)",
            message="This IP address is temporarily blocked. Please try again later.",
            help_text=""
        )
        return body, 429, {'Retry-After': str(retry_seconds)}

    def before_request_(self):
        """
        If running the server in debug mode, turn off Jinja caching.
        If there are validation errors, show the error page instead of normal content.
        Also refreshes participant progress tracking when the request is for
        the page the participant is supposed to be on.
        """
        if self.run_with_debugging:
            self.jinja_env.cache = {}

        from flask import request, session

        # Brute-force protection: ban check + probe-URL + hostile-UA detection.
        # Runs before the static-asset bypass below so requests like
        # /BOFS_static/.env still trip the probe-URL ban.
        if request.method != 'OPTIONS' and self.config.get('BRUTE_FORCE_PROTECTION', True):
            from BOFS.services import brute_force
            ip = brute_force.get_client_ip()
            if brute_force.is_banned(ip):
                return self._too_many_requests_response(brute_force.seconds_until_unban(ip))
            if brute_force.is_probe_url(request.path):
                brute_force.record_probe(ip, "probe_url", notes=request.path)
                return self._too_many_requests_response(brute_force.seconds_until_unban(ip))
            ua = request.user_agent.string or ""
            if brute_force.is_hostile_ua(ua):
                brute_force.record_probe(ip, "hostile_ua", notes=ua)
                return self._too_many_requests_response(brute_force.seconds_until_unban(ip))

        # If there are fatal validation errors, redirect all non-static routes to the error page
        if self.validation_errors and not request.path.startswith('/BOFS_static'):
            has_fatal = any(e.severity == "error" for e in self.validation_errors)
            if has_fatal:
                return render_template('error.html',
                    title="Questionnaire Configuration Errors",
                    heading="Questionnaire Configuration Errors",
                    message="BOFS found issues with your questionnaire definitions that must be fixed before the experiment can run.",
                    details=self.validation_errors,
                    help_text=Markup(
                        "<h3>How to fix</h3>"
                        "<ol>"
                        "<li>Check each error above and follow the suggestion.</li>"
                        "<li>Save your questionnaire JSON file(s).</li>"
                        "<li>Restart BOFS to re-validate.</li>"
                        "</ol>"
                        '<p>If you need help with questionnaire format, see the '
                        '<a href="https://bride-of-frankensystem.readthedocs.io/">BOFS documentation</a>.</p>'
                    )
                )

        # Participant progress tracking. Runs for every request when the
        # request is for the page the participant is supposed to be on. This
        # makes tracking robust against custom blueprint routes that forget
        # @verify_correct_page (which previously was the only writer).
        if 'participantID' in session and 'currentUrl' in session:
            currentUrl = request.url.replace(request.url_root, "")
            if currentUrl == session['currentUrl']:
                from BOFS.services.routing import ParticipantRoutingService
                ParticipantRoutingService.from_app().track_progress(currentUrl)

    # Pages whose view functions are framework-special and don't go through
    # @verify_correct_page (handled in the admin timeline as a special case).
    _PAGES_DECORATOR_NOT_REQUIRED = frozenset({
        'consent', 'consent_nc', 'create_participant', 'create_participant_nc', 'end',
    })

    def warn_undecorated_pages(self):
        """
        Emit a warning for any PAGE_LIST entry whose route is missing the
        ``@verify_correct_page`` decorator. The decorator enforces page-list
        ordering — without it, participants can land on a page out of order
        and the framework can't redirect them back. Called once at startup.
        """
        adapter = self.url_map.bind('localhost')
        for page in self.page_list.flat_page_list(condition=0):
            path = page.get('path', '')
            if not path or path in self._PAGES_DECORATOR_NOT_REQUIRED:
                continue
            try:
                endpoint, _ = adapter.match('/' + path)
            except Exception:
                self.logger.warning(
                    "PAGE_LIST entry %r doesn't match any registered route. "
                    "Participants navigating to this page will see a 404.",
                    path,
                )
                continue

            view_func = self.view_functions.get(endpoint)
            if view_func is None:
                continue
            if getattr(view_func, '_bofs_suppress_activity_polling', False):
                continue  # Researcher is managing this route manually.
            if not getattr(view_func, '_bofs_verify_correct_page', False):
                self.logger.warning(
                    "PAGE_LIST entry %r maps to view %s which is missing "
                    "@verify_correct_page. The decorator enforces page-list "
                    "ordering and bootstraps session state; without it, "
                    "participants can navigate to this page out of order.",
                    path, endpoint,
                )

    _ACTIVITY_POLL_TAG = b'<script src="/BOFS_static/js/user_active.js"></script>'
    _ACTIVITY_POLL_SKIP_PREFIXES = ('/admin', '/BOFS_static')

    def after_request_(self, response):
        """
        Inject the activity-polling ``<script>`` into HTML responses for
        participant pages. This is what keeps ``Participant.lastActiveOn``
        fresh for custom pages that don't extend ``template.html`` (and thus
        don't include the ``checkUserActive`` macro inline).

        Skipped when:
          - response is not ``text/html``
          - no participant in session
          - request path is admin or BOFS static
          - the route applied ``@suppress_activity_polling``
        """
        from flask import request, session, g

        if response.status_code != 200:
            return response
        if response.mimetype != 'text/html':
            return response
        if 'participantID' not in session:
            return response
        if request.path.startswith(self._ACTIVITY_POLL_SKIP_PREFIXES):
            return response
        if getattr(g, 'bofs_skip_activity_polling', False):
            return response
        if response.direct_passthrough:
            return response

        body = response.get_data()
        # Empty/whitespace-only responses (e.g. API endpoints that just return
        # "") aren't pages — skip silently rather than warning.
        if not body.strip():
            return response

        idx = body.rfind(b'</body>')
        if idx == -1:
            self.logger.warning(
                "BOFS activity-polling: response for %s has no </body> tag; "
                "skipping script injection. Participants on this page won't "
                "have their lastActiveOn refreshed and may be marked abandoned.",
                request.path,
            )
            return response

        response.set_data(body[:idx] + self._ACTIVITY_POLL_TAG + body[idx:])
        return response
