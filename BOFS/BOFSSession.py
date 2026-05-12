import hashlib
from flask import Request, current_app, has_app_context
from flask.sessions import SessionInterface, SessionMixin, TaggedJSONSerializer
from itsdangerous import BadData, BadSignature
from werkzeug.datastructures import CallbackDict
from uuid import uuid4
from datetime import timedelta
from . import BOFSFlask
from .util import utcnow_naive


class BOFSSessionInterface(SessionInterface):
    serializer = TaggedJSONSerializer()

    def __init__(self):
        self._cookie_name = None

    def get_cookie_name(self, app) -> str:
        """
        Per-project cookie name so two BOFS projects on the same host don't try to use each other's cookies.
        Override via SESSION_COOKIE_NAME.
        """
        if self._cookie_name is not None:
            return self._cookie_name

        override = app.config.get('SESSION_COOKIE_NAME')
        if override:
            self._cookie_name = override
        else:
            seed = (str(app.config.get('TITLE', '')) + str(app.config.get('SECRET_KEY', ''))).encode('utf-8')
            self._cookie_name = 'bofs_' + hashlib.sha256(seed).hexdigest()[:10]
        return self._cookie_name

    def create_db_object(self, app, sessionID):
        storedSession = app.db.SessionStore()
        storedSession.sessionID = sessionID
        storedSession.expiry = utcnow_naive() + timedelta(days=21)

        app.db.session.add(storedSession)
        app.db.session.commit()
        return storedSession

    def open_session(self, app: "BOFSFlask", request: "Request"):
        cookie_name = self.get_cookie_name(app)
        sessionID = request.cookies.get(cookie_name)

        # No sessionID cookie is set; create a new session.
        if not sessionID:
            sessionID = str(uuid4())
            self.create_db_object(app, sessionID)
            return BOFSSession(None, sessionID=sessionID, new=True)

        storedSession = app.db.session.get(app.db.SessionStore, sessionID)

        # The database has no session info! The cookie exists, but the session is empty.
        if not storedSession:
            self.create_db_object(app, sessionID)
            return BOFSSession(None, sessionID=sessionID, new=True)

        # The session has been expired, so let's clear out the DB and give a blank session
        if storedSession.expired:
            if has_app_context():
                current_app.logger.info(
                    "Session expired; deleting sessionID=%s.", sessionID,
                )
            app.db.session.delete(storedSession)
            app.db.session.commit()
            return BOFSSession(None, sessionID=sessionID, new=True)

        # Try to load the data from the DB into the session dict. A bad
        # signature / corrupt blob / missing data is recoverable — just hand
        # the client a fresh blank session. Log at warning (not exception)
        # because this fires on every tampered or post-key-rotation cookie
        # and would otherwise spam the log on benign traffic.
        try:
            val = storedSession.data
            data = self.serializer.loads(val)
            return BOFSSession(data, sessionID=sessionID)  # All is well.
        except (BadSignature, BadData, ValueError, TypeError) as e:
            if has_app_context():
                current_app.logger.warning(
                    "Session deserialise failed for sessionID=%s (%s); issuing blank session.",
                    sessionID, type(e).__name__,
                )
            return BOFSSession(None, sessionID=sessionID, new=True)

    def regenerate(self, app: "BOFSFlask", session) -> None:
        """Rotate the session ID, copying the session row to a fresh ID and
        deleting the old one. Call this on any privilege transition (most
        importantly admin login) so a session cookie that was visible to the
        client before authentication can't ride the post-auth session.

        Marks the session as ``new`` so :meth:`save_session` emits a fresh
        ``Set-Cookie`` header on the response.
        """
        old_id = session.sessionID
        new_id = str(uuid4())

        old_row = app.db.session.get(app.db.SessionStore, old_id) if old_id else None
        new_row = app.db.SessionStore()
        new_row.sessionID = new_id
        new_row.expiry = utcnow_naive() + timedelta(days=21)
        if old_row is not None:
            new_row.participantID = old_row.participantID
            new_row.mTurkID = old_row.mTurkID
            app.db.session.delete(old_row)
        app.db.session.add(new_row)
        app.db.session.commit()

        session.sessionID = new_id
        session.new = True
        session.modified = True

    def save_session(self, app: "BOFSFlask", session, response):
        domain = self.get_cookie_domain(app)
        #path = self.get_cookie_path(app)
        path = "/"  # We'll only ever want one cookie per project.
        cookie_name = self.get_cookie_name(app)

        # Looks like the session was deleted... delete the cookie.
        # We can't delete stuff from the DB as we don't know the ID.
        if not session:
            response.delete_cookie(cookie_name, domain=domain, path=path)
            return

        httpOnly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)

        storedSession = app.db.session.get(app.db.SessionStore, session.sessionID)

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
            response.set_cookie(cookie_name, session.sessionID,
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