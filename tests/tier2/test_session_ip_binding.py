"""Tier 2 tests for session IP binding (admin + participant).

Verifies that a stolen session cookie can't be replayed from a different IP.
"""

import json
import os

import pytest
import toml


@pytest.fixture
def bofs_app_with_admin(tmp_path):
    """BOFS app with admin enabled for testing the verify_admin IP check."""
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "BRUTE_FORCE_PROTECTION": True,
        # Tests POST directly to admin endpoints without fetching the form
        # first; disable CSRF protection so the IP-binding behavior under
        # test isn't masked by a 403 on missing token.
        "WTF_CSRF_ENABLED": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()
    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)
    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Admin session IP binding (no opt-out — always enforced)
# ---------------------------------------------------------------------------

class TestAdminSessionIpBinding:
    def test_login_sets_admin_ip(self, bofs_app_with_admin):
        client = bofs_app_with_admin.test_client()
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                    follow_redirects=False)
        with client.session_transaction() as sess:
            assert sess.get('loggedIn') is True
            assert sess.get('adminIp') == '10.0.0.1'

    def test_same_ip_admin_request_succeeds(self, bofs_app_with_admin):
        client = bofs_app_with_admin.test_client()
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                    follow_redirects=False)
        # Subsequent admin request from same IP — verify_admin should let it
        # through. We don't care if the downstream page renders; only that
        # we're not redirected back to the login page.
        resp = client.get('/admin/progress',
                          environ_base={'REMOTE_ADDR': '10.0.0.1'},
                          follow_redirects=False)
        if resp.status_code == 302:
            assert '/admin/login' not in resp.headers.get('Location', '')

    def test_different_ip_redirects_to_login(self, bofs_app_with_admin):
        client = bofs_app_with_admin.test_client()
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                    follow_redirects=False)
        # Request from a different IP with the same session cookie
        resp = client.get('/admin/progress',
                          environ_base={'REMOTE_ADDR': '10.0.0.99'},
                          follow_redirects=False)
        assert resp.status_code == 302
        assert '/admin/login' in resp.headers['Location']
        # Session was cleared
        with client.session_transaction() as sess:
            assert sess.get('loggedIn') is None
            assert sess.get('adminIp') is None

    def test_no_opt_out_for_admin(self, bofs_app_with_admin):
        """Admin IP binding should fire even when participant binding is off
        — admins shouldn't be roaming networks."""
        bofs_app_with_admin.config['SESSION_BIND_TO_IP_PARTICIPANT'] = False
        client = bofs_app_with_admin.test_client()
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                    follow_redirects=False)
        resp = client.get('/admin/progress',
                          environ_base={'REMOTE_ADDR': '10.0.0.99'},
                          follow_redirects=False)
        assert resp.status_code == 302
        assert '/admin/login' in resp.headers['Location']

    def test_protection_disabled_skips_check(self, bofs_app_with_admin):
        """Master kill-switch disables the IP check too."""
        bofs_app_with_admin.config['BRUTE_FORCE_PROTECTION'] = False
        client = bofs_app_with_admin.test_client()
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                    follow_redirects=False)
        # Request from different IP — should NOT be redirected to login because
        # protection is off, even though the IPs differ.
        resp = client.get('/admin/progress',
                          environ_base={'REMOTE_ADDR': '10.0.0.99'},
                          follow_redirects=False)
        if resp.status_code == 302:
            assert '/admin/login' not in resp.headers.get('Location', '')


# ---------------------------------------------------------------------------
# Participant session IP binding
# ---------------------------------------------------------------------------
#
# The participant IP check lives in verify_session_valid. We unit-test it
# directly rather than going through a full HTTP flow — the request context
# fixture lets us simulate a session at IP A and a request from IP B without
# wiring a custom blueprint.

class TestParticipantSessionIpBinding:
    def _make_participant(self, app, ip):
        p = app.db.Participant()
        p.ipAddress = ip
        p.userAgent = "test"
        app.db.session.add(p)
        app.db.session.commit()
        return p

    def test_same_ip_passes(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = True
        bofs_app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = True
        p = self._make_participant(bofs_app, '10.0.0.1')

        from BOFS.util import verify_session_valid

        @verify_session_valid
        def view():
            return 'OK'

        with bofs_app.test_request_context(
                '/', environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            from flask import session
            session['currentUrl'] = '/'
            session['participantID'] = p.participantID
            assert view() == 'OK'

    def test_different_ip_clears_session_and_redirects(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = True
        bofs_app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = True
        p = self._make_participant(bofs_app, '10.0.0.1')

        from BOFS.util import verify_session_valid

        @verify_session_valid
        def view():
            return 'OK'

        with bofs_app.test_request_context(
                '/', environ_base={'REMOTE_ADDR': '10.0.0.99'}):
            from flask import session
            session['currentUrl'] = '/'
            session['participantID'] = p.participantID
            response = view()
            # Werkzeug redirect response, status 302
            assert getattr(response, 'status_code', None) == 302
            # Session was cleared
            assert 'currentUrl' not in session
            assert 'participantID' not in session

    def test_opt_out_with_session_bind_disabled(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = True
        bofs_app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = False
        p = self._make_participant(bofs_app, '10.0.0.1')

        from BOFS.util import verify_session_valid

        @verify_session_valid
        def view():
            return 'OK'

        with bofs_app.test_request_context(
                '/', environ_base={'REMOTE_ADDR': '10.0.0.99'}):
            from flask import session
            session['currentUrl'] = '/'
            session['participantID'] = p.participantID
            assert view() == 'OK'

    def test_protection_disabled_skips_check(self, bofs_app):
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = False
        bofs_app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = True
        p = self._make_participant(bofs_app, '10.0.0.1')

        from BOFS.util import verify_session_valid

        @verify_session_valid
        def view():
            return 'OK'

        with bofs_app.test_request_context(
                '/', environ_base={'REMOTE_ADDR': '10.0.0.99'}):
            from flask import session
            session['currentUrl'] = '/'
            session['participantID'] = p.participantID
            assert view() == 'OK'

    def test_empty_participant_ip_is_lenient(self, bofs_app):
        """Participants created before the IP-capture path was wired (or with
        an empty REMOTE_ADDR in tests) should not be locked out by the IP
        check — only enforce when there's a stored IP to compare against."""
        bofs_app.config['BRUTE_FORCE_PROTECTION'] = True
        bofs_app.config['SESSION_BIND_TO_IP_PARTICIPANT'] = True
        p = self._make_participant(bofs_app, '')  # no stored IP

        from BOFS.util import verify_session_valid

        @verify_session_valid
        def view():
            return 'OK'

        with bofs_app.test_request_context(
                '/', environ_base={'REMOTE_ADDR': '10.0.0.99'}):
            from flask import session
            session['currentUrl'] = '/'
            session['participantID'] = p.participantID
            assert view() == 'OK'
