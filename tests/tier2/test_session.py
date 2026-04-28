"""Tier 2 tests for BOFSSession and BOFSSessionInterface.

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture from conftest.py.
"""

from datetime import timedelta

import pytest
from werkzeug.test import EnvironBuilder

from BOFS.BOFSSession import BOFSSession, BOFSSessionInterface
from BOFS.util import utcnow_naive


# ===========================================================================
# TestBOFSSession
# ===========================================================================

class TestBOFSSession:
    def test_initial_state(self):
        s = BOFSSession(None, sessionID="abc-123", new=True)
        assert s.modified is False
        assert s.new is True
        assert s.sessionID == "abc-123"

    def test_modified_tracking(self):
        s = BOFSSession(None, sessionID="abc-123", new=False)
        assert s.modified is False
        s["key"] = "value"
        assert s.modified is True

    def test_sessionID_preserved(self):
        s = BOFSSession({"foo": "bar"}, sessionID="xyz-789")
        assert s.sessionID == "xyz-789"
        assert s["foo"] == "bar"


# ===========================================================================
# TestSessionStore
# ===========================================================================

class TestSessionStore:
    def test_expired_property_true(self, bofs_app):
        store = bofs_app.db.SessionStore()
        store.sessionID = "expired-test"
        store.expiry = utcnow_naive() - timedelta(days=1)
        assert store.expired is True

    def test_expired_property_false(self, bofs_app):
        store = bofs_app.db.SessionStore()
        store.sessionID = "fresh-test"
        store.expiry = utcnow_naive() + timedelta(days=21)
        assert store.expired is False


# ===========================================================================
# TestOpenSession
# ===========================================================================

class TestOpenSession:
    def test_no_cookie_creates_new(self, bofs_app):
        interface = bofs_app.session_interface
        builder = EnvironBuilder(method="GET", path="/")
        request = builder.get_request()

        s = interface.open_session(bofs_app, request)

        assert s.new is True
        assert s.sessionID is not None
        # Should have created a SessionStore record
        stored = bofs_app.db.session.get(bofs_app.db.SessionStore, s.sessionID)
        assert stored is not None

    def test_valid_cookie_loads_data(self, bofs_app):
        interface = bofs_app.session_interface
        cookie_name = interface.get_cookie_name(bofs_app)

        # Create a session in the DB with serialized data
        session_id = "valid-session-id"
        stored = bofs_app.db.SessionStore()
        stored.sessionID = session_id
        stored.expiry = utcnow_naive() + timedelta(days=21)
        stored.data = interface.serializer.dumps({"participantID": 42})
        bofs_app.db.session.add(stored)
        bofs_app.db.session.commit()

        builder = EnvironBuilder(method="GET", path="/")
        request = builder.get_request()
        request.cookies = {cookie_name: session_id}

        s = interface.open_session(bofs_app, request)

        assert s.new is False
        assert s["participantID"] == 42

    def test_expired_session_returns_new(self, bofs_app):
        interface = bofs_app.session_interface
        cookie_name = interface.get_cookie_name(bofs_app)

        session_id = "expired-session-id"
        stored = bofs_app.db.SessionStore()
        stored.sessionID = session_id
        stored.expiry = utcnow_naive() - timedelta(days=1)
        stored.data = interface.serializer.dumps({"old": "data"})
        bofs_app.db.session.add(stored)
        bofs_app.db.session.commit()

        builder = EnvironBuilder(method="GET", path="/")
        request = builder.get_request()
        request.cookies = {cookie_name: session_id}

        s = interface.open_session(bofs_app, request)

        assert s.new is True
        # Old session should have been deleted
        old = bofs_app.db.session.get(bofs_app.db.SessionStore, session_id)
        assert old is None


# ===========================================================================
# TestSaveSession
# ===========================================================================

class TestSaveSession:
    def test_saves_modified_data(self, bofs_app):
        interface = bofs_app.session_interface

        # Create a session record in DB
        session_id = "save-test"
        db_record = interface.create_db_object(bofs_app, session_id)

        s = BOFSSession(None, sessionID=session_id, new=False)
        s["testKey"] = "testValue"  # This sets modified=True

        from werkzeug.wrappers import Response
        response = Response()
        interface.save_session(bofs_app, s, response)

        # Reload from DB and verify
        stored = bofs_app.db.session.get(bofs_app.db.SessionStore, session_id)
        data = interface.serializer.loads(stored.data)
        assert data["testKey"] == "testValue"

    def test_updates_participant_id(self, bofs_app):
        interface = bofs_app.session_interface

        session_id = "pid-sync-test"
        interface.create_db_object(bofs_app, session_id)

        s = BOFSSession(None, sessionID=session_id, new=False)
        s["participantID"] = 99  # Sets modified=True

        from werkzeug.wrappers import Response
        response = Response()
        interface.save_session(bofs_app, s, response)

        stored = bofs_app.db.session.get(bofs_app.db.SessionStore, session_id)
        assert stored.participantID == 99
