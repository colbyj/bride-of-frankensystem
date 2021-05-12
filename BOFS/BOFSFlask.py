from __future__ import print_function
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from flask import Flask, render_template, request, session, redirect, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask.config import Config
import jinja2
import json
import re
import sys
import os
from . import util
from datetime import datetime, timedelta
from .JSONQuestionnaire import JSONQuestionnaire
from .PageList import PageList
from .globals import referrer
import random


# Used to parse e.g., %20 to ' '
try:
    # Python 3
    from urllib.parse import unquote
    chr = chr
except ImportError:
    # Python 2
    from urllib.parse import unquote


class BOFSFlask(Flask):
    def __init__(self, import_name, config_name, root_path=None):
        super(BOFSFlask, self).__init__(import_name)
        if root_path:
            self.root_path = root_path

        self.config = self.make_config()
        self.load_config(config_name)
        self.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        self.page_list = PageList(self.config['PAGE_LIST'])

        bofs_path = os.path.dirname(os.path.abspath(__file__))  # Get the current working path.

        self.bofs_path = bofs_path

        self.db = SQLAlchemy(self)
        self.db_tables = []
        self.questionnaires = {}

        #self.socketio = SocketIO(self, async_mode='eventlet', manage_session=False)

        # Store Flask session in the database.
        #self.sess = Session()
        #self.config["SESSION_TYPE"] = "sqlalchemy"
        #self.config["SESSION_SQLALCHEMY"] = self.db
        self.session_interface = BOFSSessionInterface()

        self.add_url_rule("/BOFS_static/<path:filename>", endpoint="BOFS_static", view_func=self.route_BOFS_static)
        self.add_url_rule("/JSON_questionnaire/<path:filename>", endpoint="JSON_questionnaire", view_func=self.route_JSON_questionnaire)
        self.register_error_handler(404, self.page_not_found)

        # Allows developers of BOFS deployments to override BOFS templates
        my_loader = jinja2.ChoiceLoader([
            self.jinja_loader,
            jinja2.FileSystemLoader(self.bofs_path + '/templates'),
        ])

        self.jinja_loader = my_loader

        self.jinja_env.add_extension("jinja2.ext.do")

        # allows flat_page_list variable to be accessible from all templates
        self.template_context_processors[None].append(self.inject_jinja_vars)

        # properly apply content-encoding request headers for gzip and brotli
        self.after_request(self.add_headers_to_compressed)

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
            #self.socketio.run(self, host=host, port=port, **options)

    # This method is straight from Flask-SocketIO
    # (https://github.com/miguelgrinberg/Flask-SocketIO/blob/master/flask_socketio/__init__.py)
    # MIT License, Copyright holder Miguel Grinberg
    def eventlet_run(self, app, host=None, port=None, **kwargs):
        import eventlet
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
        self.config.from_pyfile(filename, silent=silent)

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

        if try_to_load_models: # Try to load the models too.
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

    def load_questionnaire(self, filename, add_to_db=False):
        if "questionnaire_" + filename in self.db.metadata.tables:
            return

        if filename in self.questionnaires:
            return

        print (filename)
        questionnaire = JSONQuestionnaire(filename)
        questionnaire.create_db_class()

        if add_to_db:
            setattr(self.db, "Questionnaire" + questionnaire.dbClass.__name__, questionnaire.dbClass)

        self.questionnaires[filename] = questionnaire
        return questionnaire

    def load_questionnaires(self, add_to_db=False):
        for page in self.page_list.get_questionnaire_list():
            self.load_questionnaire(page, add_to_db)

    # Default routes...
    def route_BOFS_static(self, filename):
        return send_from_directory(self.bofs_path + '/static', filename)

    def route_JSON_questionnaire(self, filename):
        return send_from_directory(self.root_path + '/questionnaires', filename)

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

    def add_headers_to_compressed(self, response):
        if request.path and re.search(r'\.(br)$', request.path):
            if 'Content-Type' in response.headers and re.search(r'\.(data.br)$', request.path):
                response.headers['Content-Type'] = 'application/octet-stream'
                response.status_code = 200  # Don't allow the browser to use the cached data file.
            if 'Content-Type' in response.headers and re.search(r'\.(js.br)$', request.path):
                response.headers['Content-Type'] = 'application/javascript'

            response.headers.add('Content-Encoding', 'br')

        if request.path and re.search(r'\.(gz)$', request.path):
            if 'Content-Type' in response.headers and re.search(r'\.(data.gz)$', request.path):
                response.headers['Content-Type'] = 'application/octet-stream'
                response.status_code = 200  # Don't allow the browser to use the cached data file.
            if 'Content-Type' in response.headers and re.search(r'\.(js.gz)$', request.path):
                response.headers['Content-Type'] = 'application/javascript'
            response.headers.add('Content-Encoding', 'gzip')

        return response


from flask.sessions import SessionInterface, SessionMixin, TaggedJSONSerializer
from werkzeug.datastructures import CallbackDict
from uuid import uuid4


class BOFSSessionInterface(SessionInterface):
    serializer = TaggedJSONSerializer()

    def create_db_object(self, app, sessionID):
        storedSession = app.db.SessionStore()
        storedSession.sessionID = sessionID
        storedSession.expiry = datetime.utcnow() + timedelta(days=21)

        app.db.session.add(storedSession)
        app.db.session.commit()
        return storedSession

    def open_session(self, app, request):
        sessionID = request.cookies.get("session")

        # No sessionID cookie is set; create a new session.
        if not sessionID:
            sessionID = str(uuid4())
            self.create_db_object(app, sessionID)
            return BOFSSession(None, sessionID=sessionID, new=True)

        storedSession = app.db.session.query(app.db.SessionStore).get(sessionID)

        # The database has no session info! The cookie exists, but the session is empty.
        if not storedSession:
            self.create_db_object(app, sessionID)
            return BOFSSession(None, sessionID=sessionID, new=True)

        # The session has been expired, so let's clear out the DB and give a blank session
        if storedSession.expired:
            print("Session expired; deleting it.")
            app.db.session.delete(storedSession)
            app.db.session.commit()
            return BOFSSession(None, sessionID=sessionID, new=True)

        # Try to load the data from the DB into the session dict
        try:
            val = storedSession.data
            data = self.serializer.loads(val)
            return BOFSSession(data, sessionID=sessionID)  # All is well.
        except:
            # Nope. Something bad happened; send them a blank session
            return BOFSSession(None, sessionID=sessionID, new=True)

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        #path = self.get_cookie_path(app)
        path = "/"  # We'll only ever want one cookie per project.

        # Looks like the session was deleted... delete the cookie.
        # We can't delete stuff from the DB as we don't know the ID.
        if not session:
            response.delete_cookie("session", domain=domain, path=path)
            return

        httpOnly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)

        storedSession = app.db.session.query(app.db.SessionStore).get(session.sessionID)

        # This must be a new session.
        if not storedSession:
            storedSession = self.create_db_object(app, session.sessionID)

        if session.modified:
            storedSession.data = self.serializer.dumps(dict(session))

        if 'participantID' in session:
            storedSession.participantID = session['participantID']

        if 'mTurkID' in session:
            storedSession.mTurkID = session['mTurkID']

        # Only save if there's a reason to do so.
        if session.new or session.modified:
            app.db.session.commit()

        if session.new:
            response.set_cookie("session", session.sessionID,
                                expires=storedSession.expiry, httponly=httpOnly,
                                domain=domain, path=path, secure=secure)


class BOFSSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sessionID=None, new=False):
        def on_update(self):
            self.modified = True

        # When the dictionary is modified, self.modified will be set True
        CallbackDict.__init__(self, initial, on_update)

        self.modified = False  # Starting state
        self.new = new
        self.sessionID = sessionID
