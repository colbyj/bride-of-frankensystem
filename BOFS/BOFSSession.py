from flask import Request
from flask.sessions import SessionInterface, SessionMixin, TaggedJSONSerializer
from werkzeug.datastructures import CallbackDict
from uuid import uuid4
from datetime import datetime, timedelta
from . import BOFSFlask


class BOFSSessionInterface(SessionInterface):
    serializer = TaggedJSONSerializer()

    def create_db_object(self, app, sessionID):
        storedSession = app.db.SessionStore()
        storedSession.sessionID = sessionID
        storedSession.expiry = datetime.utcnow() + timedelta(days=21)

        app.db.session.add(storedSession)
        app.db.session.commit()
        return storedSession

    def open_session(self, app: "BOFSFlask", request: "Request"):
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

    def save_session(self, app: "BOFSFlask", session, response):
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