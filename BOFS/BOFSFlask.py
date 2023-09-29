import jinja2
import json
import toml
import re
import os
import random
from flask import Flask, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_compress import Compress
from BOFS import util
from .BOFSSession import BOFSSessionInterface
from .JSONQuestionnaire import JSONQuestionnaire
from .JSONTable import JSONTable
from .PageList import PageList


class BOFSFlask(Flask):
    def __init__(self, import_name, config_name, root_path=None):
        super(BOFSFlask, self).__init__(import_name)
        if root_path:
            self.root_path = root_path

        self.config = self.make_config()
        self.load_config(config_name)
        self.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        self.page_list = PageList(self.config['PAGE_LIST'])

        self.bofs_path = os.path.dirname(__file__)  # Get the path to where the BOFS files (like this file) are
        self.instance_path = os.path.dirname(os.path.abspath(config_name))  # Get the current working path.

        self.db = SQLAlchemy(self)
        self.db_tables = []
        self.questionnaires = {}
        self.tables = {}

        self.compress = Compress(self)

        # Store Flask session in the database.
        self.session_interface = BOFSSessionInterface()

        self.add_url_rule("/BOFS_static/<path:filename>", endpoint="BOFS_static", view_func=self.route_BOFS_static)
        self.add_url_rule("/JSON_questionnaire/<path:filename>", endpoint="JSON_questionnaire", view_func=self.route_JSON_questionnaire)
        self.add_url_rule("/consent.html", endpoint="consent_html", view_func=self.route_consent)
        self.register_error_handler(404, self.page_not_found)

        default_templates_path = os.path.join(self.bofs_path, "templates")
        project_templates_path = os.path.join(self.instance_path, 'templates')

        # Allows developers of BOFS deployments to override BOFS templates
        my_loader = jinja2.ChoiceLoader([
            self.jinja_loader,
            jinja2.FileSystemLoader(default_templates_path),
            jinja2.FileSystemLoader(project_templates_path),
        ])

        self.jinja_loader = my_loader

        self.jinja_env.add_extension("jinja2.ext.do")

        # allows flat_page_list variable to be accessible from all templates
        self.template_context_processors[None].append(self.inject_jinja_vars)

    # Overriding this ensures compatibility with existing run.py files regardless of whether socketio is used or not
    def run(self, host=None, port=None, **options):
        print("Running on http://{}:{}".format(host if not host is None else '127.0.0.1', port if port is not None else 5000))
        if self.debug:
            self.debug = True

            print('\033[91m' + '\033[1m')  # Start red text
            print("!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!")
            print(" Debugging mode is enabled. ")
            print(" If you are deploying online please set app.debug=False")
            print("!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!")
            print('\033[0m')  # End the red

            super(BOFSFlask, self).run(host, port, use_reloader=False, **options)
        else:
            self.eventlet_run(self, host=host, port=port, **options)

    # This method is straight from Flask-SocketIO
    # (https://github.com/miguelgrinberg/Flask-SocketIO/blob/master/flask_socketio/__init__.py)
    # MIT License, Copyright holder Miguel Grinberg
    def eventlet_run(self, app, host=None, port=None, **kwargs):
        import eventlet.wsgi
        import eventlet.green
        addresses = eventlet.green.socket.getaddrinfo(host, port)
        if not addresses:
            raise RuntimeError('Could not resolve host to a valid address')
        eventlet_socket = eventlet.listen(addresses[0][4], addresses[0][0])

        # If provided an SSL argument, use an SSL socket
        ssl_args = ['keyfile', 'certfile', 'server_side', 'cert_reqs',
                    'ssl_version', 'ca_certs',
                    'do_handshake_on_connect', 'suppress_ragged_eofs',
                    'ciphers']
        ssl_params = {k: kwargs[k] for k in kwargs if k in ssl_args}
        if len(ssl_params) > 0:
            for k in ssl_params:
                kwargs.pop(k)
            ssl_params['server_side'] = True  # Listening requires true
            eventlet_socket = eventlet.wrap_ssl(eventlet_socket, **ssl_params)

        eventlet.wsgi.server(eventlet_socket, app, **kwargs)

    def load_config(self, filename, silent=False):
        if filename.endswith(".cfg"):
            self.config.from_pyfile(filename, silent=silent)
        elif filename.endswith(".toml"):
            self.config.from_file(filename, load=toml.load)
        elif filename.endswith(".json"):
            self.config.from_file(filename, load=json.load)
        else:
            print("Error: Cannot load configuration file.")

    def load_blueprint(self, blueprint_path, blueprint_name=None, try_to_load_models=True):
        print("Loading blueprint: %s" % blueprint_path)

        if blueprint_name is None:
            blueprint_name = blueprint_path

        blueprint = __import__(blueprint_path + ".views", fromlist=["views"])
        blueprint_var = getattr(blueprint, blueprint_name)
        self.register_blueprint(blueprint_var)

        try:
            self.config['ADDITIONAL_ADMIN_PAGES'] += blueprint.ADDITIONAL_ADMIN_PAGES
        except:
            pass  # No Admin pages to add

        try:
            self.config['EXPORT'] += blueprint.EXPORT
        except:
            pass  # No exports to add

        if try_to_load_models:  # Try to load the models too.
            self.load_models(blueprint_path)

    def load_models(self, blueprint_path):
        try:
            module = __import__(blueprint_path + ".models", fromlist=["models"])

            create_function = getattr(module, "create")

            if create_function is None:
                print("Warning: %s.models does not contain a `create()` function! No models will be added.")
                return

            my_classes = create_function(self.db)

            if hasattr(my_classes, '__iter__'):  # A list or tuple was returned
                for c in my_classes:
                    setattr(self.db, c.__name__, c)
                    if self.debug:
                        print("%s: Loaded %s" % (blueprint_path, c))
            else:
                setattr(self.db, my_classes.__name__, my_classes)
                if self.debug:
                    print("%s: Loaded %s" % (blueprint_path, my_classes))

            print("%s: `models.py` loaded!" % blueprint_path)
        except ImportError:
            print("%s: `models.py` not found. Add a `models.py` file to your blueprint folder use this feature." % blueprint_path)

    def load_table(self, filename):
        if filename in self.db.metadata.tables:
            return

        if filename in self.tables:
            return

        print(filename)
        table = JSONTable(filename)
        table.create_db_class()
        exports_dict = table.create_exports_dict()

        if exports_dict is not None:
            self.config['EXPORT'] += exports_dict

        # Add the table as a database class, if it hasn't been added already.
        if not hasattr(self.db, table.dbClass.__name__):
            setattr(self.db, table.dbClass.__name__, table.dbClass)

        self.tables[filename] = table
        return table

    def load_tables(self):
        tableFilenames = []

        if os.path.exists(self.root_path + "/tables"):
            for q in os.listdir(self.root_path + "/tables"):
                if q.endswith(".json"):
                    tableFilenames.append(q.replace(".json", ""))

        for tableFilename in tableFilenames:
            self.load_table(tableFilename)

    def load_questionnaire(self, filename, add_to_db=False):
        if "questionnaire_" + filename in self.db.metadata.tables:
            return

        if filename in self.questionnaires:
            return

        print(filename)
        questionnaire = JSONQuestionnaire(filename)
        questionnaire.create_db_class()

        if add_to_db:
            setattr(self.db, "Questionnaire" + questionnaire.dbClass.__name__, questionnaire.dbClass)

        self.questionnaires[filename] = questionnaire
        return questionnaire

    def questionnaire_list_is_safe(self):
        """
        Checks to see if the questionnaire list has any duplicates.
        :return True if a duplicate was found, False otherwise.
        """
        questionnaires = self.page_list.get_questionnaire_list(include_tags=True)
        return len(set(questionnaires)) == len(questionnaires)

    def load_questionnaires(self, add_to_db=False):
        for page in self.page_list.get_questionnaire_list():
            self.load_questionnaire(page, add_to_db)

    # Default routes...
    def route_BOFS_static(self, filename):
        return send_from_directory(self.bofs_path + '/static', filename)

    def route_JSON_questionnaire(self, filename):
        return send_from_directory(self.root_path + '/questionnaires', filename)

    def route_consent(self):
        return send_from_directory(self.root_path, "consent.html")

    def page_not_found(self, e):
        return "Could not load the requested page. If you are just starting out, " \
               "please click <a href=\"/restart\"><b>here</b></a> to reset your cookies for this page. " \
               "If that doesn't work, please clear your cookies or switch web browsers.", 404

    def inject_jinja_vars(self):
        return dict(
            flat_page_list=self.page_list.flat_page_list(),
            debug=self.debug,
            shuffle=random.shuffle,
            crumbs=util.create_breadcrumbs(),
            json_dumps=json.dumps
        )
