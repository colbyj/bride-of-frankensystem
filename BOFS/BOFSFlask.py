from datetime import datetime
from crawlerdetect import CrawlerDetect
import jinja2
import json
import os
import random
from typing import Union
from flask import Flask, send_from_directory, Response, url_for, render_template, session, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_compress import Compress
from markupsafe import Markup
from BOFS import util
from . import startup
from .BOFSSession import BOFSSessionInterface
from .JSONQuestionnaire import JSONQuestionnaire
from .JSONTable import JSONTable
from .PageList import PageList
from .setup_diagnostics import DiagnosticCollector


# Participant entry-point paths. The non-fatal-warning interstitial fires
# on a fresh GET to any of these, before a participantID exists in the
# session. Keeping the set tight ensures the interstitial can't appear in
# the middle of an experiment flow (it would be confusing) and never on
# admin or static routes (it would be annoying).
_LANDING_PATHS = frozenset({
    "", "consent", "consent_nc",
    "create_participant", "create_participant_nc",
    "external_id", "startMTurk", "start_mturk",
})


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

        self.setup_diagnostics = DiagnosticCollector(self)
        """Central collector for all setup-time warnings, errors, and notices.

        Surfaces on the landing-page interstitial, on the fatal-error
        page, and (planned) on an admin diagnostics page. Replaces the
        older ``validation_errors`` list, which now reads from this
        collector via the property below."""

        self.add_url_rule("/BOFS_static/<path:filename>", endpoint="BOFS_static", view_func=self.route_BOFS_static)
        self.add_url_rule("/consent.html", endpoint="consent_html", view_func=self.route_consent)
        self.add_url_rule(
            "/acknowledge_setup_diagnostics",
            endpoint="acknowledge_setup_diagnostics",
            view_func=self.route_acknowledge_setup_diagnostics,
        )
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

    @property
    def validation_errors(self):
        """Back-compat shim for the older list of validation findings.

        Returns the error+warning subset of :attr:`setup_diagnostics`.
        New code should write to ``setup_diagnostics`` directly. This
        property is read-only — historical writers (``.append`` /
        ``.extend``) have been migrated to the collector; mutating the
        returned list has no effect on the collector.
        """
        return self.setup_diagnostics.actionable()

    # ---- Pass-through methods to BOFS.startup ----
    # The implementations live in BOFS/startup.py so the BOFSFlask class
    # stays focused on Flask-subclass concerns. These thin wrappers preserve
    # the historical method form (``app.load_questionnaires()``) so
    # researcher blueprints and existing call sites keep working.

    def load_config(self, filename, silent=False) -> None:
        return startup.load_config(self, filename, silent)

    def load_empty_blueprint(self, blueprint_path) -> None:
        return startup.load_empty_blueprint(self, blueprint_path)

    def load_blueprint(self, blueprint_path, blueprint_name=None, try_to_load_models=True) -> None:
        return startup.load_blueprint(self, blueprint_path, blueprint_name, try_to_load_models)

    def load_models(self, blueprint_path) -> None:
        return startup.load_models(self, blueprint_path)

    def load_table(self, directory: str, filename: str) -> Union[JSONTable, None]:
        return startup.load_table(self, directory, filename)

    def find_files_in_app_and_blueprints(self, folder_name: str, extension: str = ".json") -> dict[str, list[str]]:
        return startup.find_files_in_app_and_blueprints(self, folder_name, extension)

    def load_tables(self) -> None:
        return startup.load_tables(self)

    def load_questionnaire(self, directory: str, filename: str, add_to_db=False,
                           valid_question_types=None) -> Union[JSONQuestionnaire, None]:
        return startup.load_questionnaire(self, directory, filename, add_to_db, valid_question_types)

    def questionnaire_list_is_safe(self) -> bool:
        return startup.questionnaire_list_is_safe(self)

    def load_questionnaires(self) -> None:
        return startup.load_questionnaires(self)

    def get_questionnaire_path(self, questionnaire_to_find) -> Union[str, None]:
        return startup.get_questionnaire_path(self, questionnaire_to_find)

    # Default routes...
    def route_BOFS_static(self, filename) -> Response:
        return send_from_directory(self.bofs_path + '/static', filename)

    def route_consent(self) -> Response:
        return send_from_directory(self.root_path, "consent.html")

    def route_acknowledge_setup_diagnostics(self):
        """Set the session flag and bounce back to the requested landing
        URL. The flag is per-session, so each fresh browser session sees
        the warnings once."""
        session["setup_diagnostics_acknowledged"] = True
        target = request.args.get("next", "/")
        # Defend against open-redirect: only allow same-origin relative
        # paths starting with a single '/'. Anything else falls back to
        # the project root.
        if not isinstance(target, str) or not target.startswith("/") or target.startswith("//"):
            target = "/"
        return redirect(target)

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

        # If setup diagnostics include any errors, block every non-static route
        # until the researcher fixes them. The fatal-error page also lists
        # any warnings alongside, since the researcher is already looking.
        if self.setup_diagnostics.has_fatal() and not request.path.startswith('/BOFS_static'):
            return render_template('error.html',
                title="Configuration Errors",
                heading="BOFS Configuration Errors",
                message="Your project has issues that must be fixed before it can run.",
                grouped=self.setup_diagnostics.grouped(),
                help_text=Markup(
                    "<h3>How to fix</h3>"
                    "<ol>"
                    "<li>Check each error above and follow the suggestion.</li>"
                    "<li>Save your configuration / questionnaire / table file(s).</li>"
                    "<li>Restart BOFS to re-validate.</li>"
                    "</ol>"
                    '<p>If you need help, see the '
                    '<a href="https://bride-of-frankensystem.readthedocs.io/">BOFS documentation</a>.</p>'
                )
            )

        # Non-fatal warnings: show a one-time interstitial on the participant
        # entry routes so the researcher sees them while testing. The
        # interstitial only fires before a participant has been created
        # (no participantID in session yet) and is acknowledged with a
        # session flag so subsequent loads, retries, and real participants
        # never re-encounter it.
        #
        # Audience gate: in production, real participants should not see
        # researcher-facing warnings. The interstitial only renders when
        # the app is running with ``-d`` (debug mode) or when the request
        # came from the loopback address — both situations indicate the
        # researcher is the one looking at the page.
        client_is_local = request.remote_addr in ("127.0.0.1", "::1", "localhost")
        researcher_is_looking = self.run_with_debugging or client_is_local
        if (
            researcher_is_looking
            and self.setup_diagnostics.by_severity("warning")
            and request.method == "GET"
            and request.path.lstrip("/") in _LANDING_PATHS
            and "participantID" not in session
            and not session.get("setup_diagnostics_acknowledged")
        ):
            return render_template(
                "error.html",
                title="BOFS Setup Warnings",
                heading="BOFS Setup Warnings",
                message=(
                    "Your project has one or more warnings that should be reviewed before launching the study."
                ),
                grouped=self.setup_diagnostics.grouped(severities=("warning",)),
                continue_url=(
                    "/acknowledge_setup_diagnostics?next="
                    + request.full_path.rstrip("?")
                ),
                help_text=Markup(
                    "<h3>What to do</h3>"
                    "<ol>"
                    "<li>Review each warning above and follow the suggestion.</li>"
                    "<li>Save your file(s) and restart BOFS to re-validate.</li>"
                    "<li>If you intend to leave a warning unresolved, you can "
                    "continue to the study below.</li>"
                    "</ol>"
                ),
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

    def warn_undecorated_pages(self) -> None:
        return startup.warn_undecorated_pages(self)

    def warn_about_unused_binds(self) -> None:
        return startup.warn_about_unused_binds(self)

    def warn_about_orphan_participants(self) -> None:
        return startup.warn_about_orphan_participants(self)

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
