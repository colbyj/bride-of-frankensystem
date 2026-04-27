"""Tier 2 tests for the activity-polling script injection in
``BOFSFlask.after_request_`` and the ``suppress_activity_polling`` decorator.

The hook injects ``<script src="/BOFS_static/js/user_active.js"></script>``
before ``</body>`` for participant-flow HTML responses, so custom pages that
don't extend ``template.html`` still refresh ``lastActiveOn``.
"""

from flask import Response, g, session

from BOFS.util import suppress_activity_polling


SCRIPT_TAG = b'<script src="/BOFS_static/js/user_active.js"></script>'


def _html_response(body=b"<html><body>hi</body></html>"):
    r = Response(body)
    r.mimetype = "text/html"
    return r


# ===========================================================================
# Injection — happy path and skip conditions
# ===========================================================================

class TestActivityInjection:
    def test_injects_for_participant_html_response(self, bofs_app):
        with bofs_app.test_request_context("/some_custom_page"):
            session['participantID'] = 1
            resp = bofs_app.after_request_(_html_response())

        assert SCRIPT_TAG in resp.get_data()
        # Must be inserted *before* </body>
        body = resp.get_data()
        assert body.index(SCRIPT_TAG) < body.index(b"</body>")

    def test_skips_when_no_participant(self, bofs_app):
        with bofs_app.test_request_context("/some_custom_page"):
            resp = bofs_app.after_request_(_html_response())

        assert SCRIPT_TAG not in resp.get_data()

    def test_skips_admin_paths(self, bofs_app):
        with bofs_app.test_request_context("/admin/dashboard"):
            session['participantID'] = 1
            resp = bofs_app.after_request_(_html_response())

        assert SCRIPT_TAG not in resp.get_data()

    def test_skips_bofs_static_paths(self, bofs_app):
        with bofs_app.test_request_context("/BOFS_static/js/jquery-3.7.1.min.js"):
            session['participantID'] = 1
            resp = bofs_app.after_request_(_html_response())

        assert SCRIPT_TAG not in resp.get_data()

    def test_skips_non_html_response(self, bofs_app):
        with bofs_app.test_request_context("/some_endpoint"):
            session['participantID'] = 1
            json_resp = Response(b'{"ok": true}', mimetype="application/json")
            resp = bofs_app.after_request_(json_resp)

        assert SCRIPT_TAG not in resp.get_data()

    def test_skips_when_decorator_flag_set(self, bofs_app):
        with bofs_app.test_request_context("/custom_unity_task"):
            session['participantID'] = 1
            g.bofs_skip_activity_polling = True
            resp = bofs_app.after_request_(_html_response())

        assert SCRIPT_TAG not in resp.get_data()

    def test_logs_warning_when_no_closing_body(self, bofs_app, caplog):
        bare = Response(b"<p>fragment with no body tag</p>", mimetype="text/html")
        with bofs_app.test_request_context("/fragmentary_page"):
            session['participantID'] = 1
            with caplog.at_level("WARNING"):
                resp = bofs_app.after_request_(bare)

        assert SCRIPT_TAG not in resp.get_data()
        assert any(
            "no </body>" in rec.message and "/fragmentary_page" in rec.message
            for rec in caplog.records
        )

    def test_silent_skip_for_empty_response(self, bofs_app, caplog):
        # API endpoints that return "" (e.g. JSONTable.handle_post) are
        # technically text/html but shouldn't trigger a warning.
        empty = Response(b"", mimetype="text/html")
        with bofs_app.test_request_context("/table/my_task"):
            session['participantID'] = 1
            with caplog.at_level("WARNING"):
                resp = bofs_app.after_request_(empty)

        assert resp.get_data() == b""
        assert not any("activity-polling" in rec.message for rec in caplog.records)

    def test_silent_skip_for_whitespace_only_response(self, bofs_app, caplog):
        ws = Response(b"   \n\t  ", mimetype="text/html")
        with bofs_app.test_request_context("/some_endpoint"):
            session['participantID'] = 1
            with caplog.at_level("WARNING"):
                resp = bofs_app.after_request_(ws)

        assert SCRIPT_TAG not in resp.get_data()
        assert not any("activity-polling" in rec.message for rec in caplog.records)

    def test_inserts_before_last_body_tag(self, bofs_app):
        # If a page has nested </body> mentions in text content, we should
        # insert before the *last* one (the real closing tag).
        body = b"<html><body>see &lt;/body&gt; in text<br></body></html>"
        with bofs_app.test_request_context("/page"):
            session['participantID'] = 1
            resp = bofs_app.after_request_(Response(body, mimetype="text/html"))

        out = resp.get_data()
        assert out.count(SCRIPT_TAG) == 1
        assert out.rindex(SCRIPT_TAG) < out.rindex(b"</body>")


# ===========================================================================
# Decorator
# ===========================================================================

class TestSuppressActivityPolling:
    def test_decorator_sets_flag(self, bofs_app):
        @suppress_activity_polling
        def view():
            return "ok"

        with bofs_app.test_request_context("/something"):
            assert getattr(g, "bofs_skip_activity_polling", False) is False
            view()
            assert g.bofs_skip_activity_polling is True

    def test_decorator_preserves_return_value(self, bofs_app):
        @suppress_activity_polling
        def view():
            return "hello"

        with bofs_app.test_request_context("/something"):
            assert view() == "hello"
