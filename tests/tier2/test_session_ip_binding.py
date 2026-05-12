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
# Admin login session fixation protection
# ---------------------------------------------------------------------------

class TestAdminLoginSessionRotation:
    def _cookie_name(self, app):
        return app.session_interface.get_cookie_name(app)

    def _extract_cookie(self, response, name):
        """Return the cookie value from a Set-Cookie header, or None."""
        # Werkzeug's test client exposes headers via .headers.get_all
        for header, value in response.headers.items():
            if header.lower() != 'set-cookie':
                continue
            if value.startswith(name + '='):
                # 'name=value; Path=/; ...'
                return value.split(';', 1)[0].split('=', 1)[1]
        return None

    def test_login_rotates_session_id(self, bofs_app_with_admin):
        """A session cookie planted before login must not survive login —
        the post-auth session must be served under a fresh ID."""
        app = bofs_app_with_admin
        client = app.test_client()
        cookie_name = self._cookie_name(app)

        # Step 1: GET /admin/login to plant a pre-auth session cookie.
        get_resp = client.get('/admin/login',
                              environ_base={'REMOTE_ADDR': '10.0.0.1'})
        pre_auth_id = self._extract_cookie(get_resp, cookie_name)
        assert pre_auth_id is not None, "expected a pre-auth session cookie"

        # Step 2: POST credentials. Login must respond with a fresh cookie.
        post_resp = client.post('/admin/login',
                                data={'password': 'test'},
                                environ_base={'REMOTE_ADDR': '10.0.0.1'},
                                follow_redirects=False)
        post_auth_id = self._extract_cookie(post_resp, cookie_name)
        assert post_auth_id is not None, "login did not Set-Cookie"
        assert post_auth_id != pre_auth_id, (
            "session ID was not rotated on login — vulnerable to session fixation"
        )

        # Step 3: the old session row is gone, and the new one is loggedIn=True.
        old_row = app.db.session.get(app.db.SessionStore, pre_auth_id)
        assert old_row is None, "pre-auth session row was not deleted"
        new_row = app.db.session.get(app.db.SessionStore, post_auth_id)
        assert new_row is not None


# ---------------------------------------------------------------------------
# Admin logout
# ---------------------------------------------------------------------------

class TestAdminLogout:
    def _login(self, client, ip='10.0.0.1'):
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': ip},
                    follow_redirects=False)

    def test_logout_clears_loggedin_and_deletes_session_row(self, bofs_app_with_admin):
        app = bofs_app_with_admin
        client = app.test_client()
        self._login(client)

        cookie_name = app.session_interface.get_cookie_name(app)
        cookie = client.get_cookie(cookie_name)
        assert cookie is not None
        sid_before = cookie.value
        # Sanity: SessionStore row exists, session has loggedIn.
        assert app.db.session.get(app.db.SessionStore, sid_before) is not None
        with client.session_transaction() as sess:
            assert sess.get('loggedIn') is True

        resp = client.post('/admin/logout',
                           environ_base={'REMOTE_ADDR': '10.0.0.1'},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert '/admin/login' in resp.headers['Location']

        # SessionStore row is gone.
        assert app.db.session.get(app.db.SessionStore, sid_before) is None
        # Session no longer marks the user as admin.
        with client.session_transaction() as sess:
            assert sess.get('loggedIn') is None
            assert sess.get('adminIp') is None

    def test_logout_requires_post(self, bofs_app_with_admin):
        """GET on /admin/logout returns 405 — prevents drive-by logout via
        phishing link."""
        app = bofs_app_with_admin
        client = app.test_client()
        self._login(client)

        resp = client.get('/admin/logout',
                          environ_base={'REMOTE_ADDR': '10.0.0.1'},
                          follow_redirects=False)
        assert resp.status_code == 405

    def test_logout_requires_admin(self, bofs_app_with_admin):
        """Anonymous POST to /admin/logout redirects to login (verify_admin)."""
        app = bofs_app_with_admin
        client = app.test_client()
        # Not logged in.
        resp = client.post('/admin/logout',
                           environ_base={'REMOTE_ADDR': '10.0.0.1'},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert '/admin/login' in resp.headers['Location']


# ---------------------------------------------------------------------------
# Admin /logged_in is gated
# ---------------------------------------------------------------------------

class TestAdminLoggedInGated:
    def test_anonymous_does_not_see_True(self, bofs_app_with_admin):
        """An unauthenticated probe must not get a 'True' response — the
        endpoint used to leak admin presence to anyone with cookie access."""
        client = bofs_app_with_admin.test_client()
        resp = client.get('/admin/logged_in',
                          environ_base={'REMOTE_ADDR': '10.0.0.1'},
                          follow_redirects=False)
        # verify_admin redirects to /admin/login when not logged in.
        assert resp.status_code == 302
        assert '/admin/login' in resp.headers['Location']
        # Body is a redirect stub, not "True".
        assert b'True' not in resp.data or resp.status_code != 200

    def test_authenticated_returns_True(self, bofs_app_with_admin):
        client = bofs_app_with_admin.test_client()
        client.post('/admin/login', data={'password': 'test'},
                    environ_base={'REMOTE_ADDR': '10.0.0.1'},
                    follow_redirects=False)
        resp = client.get('/admin/logged_in',
                          environ_base={'REMOTE_ADDR': '10.0.0.1'},
                          follow_redirects=False)
        assert resp.status_code == 200
        assert resp.data == b'True'


# ---------------------------------------------------------------------------
# /admin/login?r= open redirect
# ---------------------------------------------------------------------------

class TestAdminLoginRedirectParam:
    def _login(self, client, r=None):
        url = '/admin/login'
        if r is not None:
            from urllib.parse import quote
            url += '?r=' + quote(r)
        return client.post(url, data={'password': 'test'},
                           environ_base={'REMOTE_ADDR': '10.0.0.1'},
                           follow_redirects=False)

    def test_valid_r_redirects_to_endpoint(self, bofs_app_with_admin):
        resp = self._login(bofs_app_with_admin.test_client(), r='route_export')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/admin/export')

    def test_malformed_r_falls_back_to_default(self, bofs_app_with_admin):
        """A value that doesn't match [A-Za-z_][A-Za-z0-9_]* (e.g. contains a
        slash) must not be passed to url_for at all — fall back to the
        default landing page."""
        # Crafted to try to escape the admin blueprint.
        for bad in ['../route_progress', 'route_progress?x=1',
                    'route progress', '', 'route-progress',
                    '__class__', 'route_progress\nset-cookie']:
            resp = self._login(bofs_app_with_admin.test_client(), r=bad)
            assert resp.status_code == 302
            # Falls back to route_progress regardless of input.
            assert resp.headers['Location'].endswith('/admin/progress'), (
                f"unsafe r={bad!r} did not fall back to default"
            )

    def test_unknown_endpoint_falls_back(self, bofs_app_with_admin):
        """Valid identifier but no such endpoint — BuildError caught, default
        landing page used."""
        resp = self._login(bofs_app_with_admin.test_client(),
                           r='no_such_admin_route')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/admin/progress')


# ---------------------------------------------------------------------------
# Researcher-authored doi is not rendered as raw HTML
# ---------------------------------------------------------------------------

class TestDoiRendering:
    """The questionnaire-preview template used to render q.doi inside an
    ``a href`` with ``|safe``, allowing a researcher-authored DOI to inject
    script into the admin's browser. Regression: render the relevant
    snippet directly with attack payloads and confirm no executable markup
    survives autoescape."""

    # The exact snippet (sans whitespace) from preview_questionnaire.html.
    # If this fails, somebody re-introduced |safe or changed the scheme guard.
    _DOI_SNIPPET = (
        "{% if q.doi %}"
        "<li><b>DOI: </b>"
        "{% if q.doi.startswith(\"http://\") or q.doi.startswith(\"https://\") %}"
        "<a href=\"{{ q.doi }}\">{{ q.doi }}</a>"
        "{% else %}"
        "<a href=\"https://doi.org/{{ q.doi }}\">https://doi.org/{{ q.doi }}</a>"
        "{% endif %}"
        "</li>{% endif %}"
    )

    def _render(self, app, doi):
        from flask import render_template_string
        with app.test_request_context('/'):
            return render_template_string(
                self._DOI_SNIPPET,
                q=type("Q", (), {"doi": doi}),
            )

    def test_script_tag_in_doi_is_escaped(self, bofs_app):
        payload = '"><script>alert(1)</script>'
        rendered = self._render(bofs_app, payload)
        # No raw <script> tag should appear; '<' must be escaped to &lt;.
        assert '<script>' not in rendered
        assert '&lt;script&gt;' in rendered

    def test_attribute_injection_is_escaped(self, bofs_app):
        # Tries to escape the href attribute and inject an onclick handler.
        # Jinja's autoescape encodes the closing `"` to `&#34;` (or `&quot;`),
        # so the injected content stays inside the href value and is not
        # parsed as an attribute by the browser.
        payload = '" onclick=alert(1) x="'
        rendered = self._render(bofs_app, payload)
        assert '&#34;' in rendered or '&quot;' in rendered, (
            "double quotes in doi must be entity-encoded in attribute context"
        )
        # A raw, unescaped quote-then-attribute sequence would look like
        # `" onclick=` directly in the output — that's the actual breakout
        # signature, and it must not appear.
        assert '" onclick=' not in rendered

    def test_http_scheme_passes_through(self, bofs_app):
        rendered = self._render(bofs_app, "https://doi.org/10.1234/x.5")
        assert 'href="https://doi.org/10.1234/x.5"' in rendered
        # Not double-prefixed.
        assert 'doi.org/https://' not in rendered

    def test_bare_doi_is_prefixed(self, bofs_app):
        rendered = self._render(bofs_app, "10.1234/x.5")
        assert 'href="https://doi.org/10.1234/x.5"' in rendered

    def test_misleading_scheme_does_not_bypass(self, bofs_app):
        """Old guard was startswith('http'), which would have admitted
        ``httpevil://``. The new guard requires the full ``http://`` or
        ``https://`` prefix, so a string starting with bare 'http' falls
        through to the doi.org-prefixed branch."""
        rendered = self._render(bofs_app, "httpevil://x")
        assert 'href="https://doi.org/httpevil://x"' in rendered


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
