"""Tier 2 tests for end reasons, the parameterized /end/<reason> route,
per-PAGE_LIST-entry outgoing_url redirects, and the framework wire-ins
(bot, no_consent, quota_full, duplicate).

Companion file to test_lazy_creation_and_cold_end.py — that one covers
cold-hit safety and lazy creation; this one covers the end_reason column
and routing behaviors built on top.
"""

import json
import os

import pytest
import toml


SIMPLE_QUESTIONNAIRE = {
    "title": "Demographics",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "answer"},
    ],
}


def _write_consent_stub(tmp_path):
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")


def _make_app(tmp_path, config_overrides, debug=False):
    base = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
    }
    base.update(config_overrides)
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(base), encoding="utf-8")

    original_cwd = os.getcwd()
    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=debug)
    ctx = app.app_context()
    ctx.push()
    return app, ctx, original_cwd


def _teardown(app, ctx, original_cwd):
    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


def _seed_participant(app, ip="127.0.0.1", **kwargs):
    """Create and commit a participant directly. Used to simulate an
    in-flow participant without going through provide_consent."""
    from BOFS.util import utcnow_naive
    p = app.db.Participant()
    p.ipAddress = ip
    p.userAgent = "test"
    p.condition = kwargs.get("condition", 0)
    p.finished = kwargs.get("finished", False)
    p.timeStarted = utcnow_naive()
    for key, value in kwargs.items():
        if key in ("condition", "finished"):
            continue
        setattr(p, key, value)
    app.db.session.add(p)
    app.db.session.commit()
    return p


# ---------------------------------------------------------------------------
# End-reason stamping and template/redirect resolution
# ---------------------------------------------------------------------------

class TestEndReasonStamping:

    def test_default_end_stamps_complete(self, tmp_path):
        """A participant hitting /end without a reason segment is stamped
        with end_reason='complete'."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end"

            response = client.get("/end")
            assert response.status_code == 200

            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.end_reason == "complete"
            assert refreshed.finished is True
        finally:
            _teardown(app, ctx, cwd)

    def test_parameterized_end_stamps_reason(self, tmp_path):
        """A participant hitting /end/<reason> is stamped with that reason."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end/screened_out"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end/screened_out"

            response = client.get("/end/screened_out")
            assert response.status_code == 200

            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.end_reason == "screened_out"
            assert refreshed.finished is True
        finally:
            _teardown(app, ctx, cwd)

    def test_per_reason_template_renders_with_chrome(self, tmp_path):
        """When ``templates/end/<reason>.html`` exists, it's rendered as a
        fragment wrapped by ``end.html`` -- same DX as ``/simple/<page>``.
        Researchers write the body content; the BOFS chrome (title bar,
        no breadcrumb on /end pages) is applied automatically."""
        _write_consent_stub(tmp_path)
        end_dir = tmp_path / "templates" / "end"
        end_dir.mkdir(parents=True)
        (end_dir / "screened_out.html").write_text(
            "<h2 id=\"reason-marker\">You were screened out</h2>",
            encoding="utf-8",
        )
        app, ctx, cwd = _make_app(tmp_path, {
            "TITLE": "Chrome Test Study",
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end/screened_out"},
            ],
        })
        try:
            p = _seed_participant(app)
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = p.participantID
                sess["currentUrl"] = "end/screened_out"

            response = client.get("/end/screened_out")
            assert response.status_code == 200
            body = response.data.decode("utf-8")

            # Researcher fragment is in the body.
            assert "You were screened out" in body
            assert "reason-marker" in body
            # BOFS chrome is wrapped around it: the title bar from
            # template.html shows the configured study title.
            assert "Chrome Test Study" in body
            # No breadcrumb on /end pages -- the breadcrumb arrow character
            # in template.html shouldn't appear.
            assert "→" not in body
        finally:
            _teardown(app, ctx, cwd)

    def test_per_reason_template_from_blueprint_directory(self, tmp_path):
        """Per-reason templates can also live under a blueprint's
        ``templates/end/<reason>.html``. BOFS's blueprint auto-discovery
        registers every project subdirectory as either a real or empty
        blueprint (see ``create_app.py:182-201``), and the resulting
        loader chain searches blueprint template folders the same way
        the simple/custom/instructions routes do."""
        _write_consent_stub(tmp_path)
        # Create a subdirectory that BOFS will auto-discover as a
        # blueprint. No views.py → it's loaded as an empty blueprint
        # that exists solely for its template folder.
        bp_dir = tmp_path / "my_blueprint"
        bp_end_dir = bp_dir / "templates" / "end"
        bp_end_dir.mkdir(parents=True)
        (bp_end_dir / "from_blueprint.html").write_text(
            "<div id=\"bp-marker\">Blueprint-supplied end page</div>",
            encoding="utf-8",
        )
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end/from_blueprint"},
            ],
        })
        try:
            p = _seed_participant(app)
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = p.participantID
                sess["currentUrl"] = "end/from_blueprint"

            response = client.get("/end/from_blueprint")
            assert response.status_code == 200
            body = response.data.decode("utf-8")
            assert "Blueprint-supplied end page" in body
            assert "bp-marker" in body
        finally:
            _teardown(app, ctx, cwd)

    def test_default_end_no_breadcrumb(self, tmp_path):
        """The default /end page (no per-reason template) also omits the
        breadcrumb. Same rule applies regardless of which template
        renders -- end pages are terminal, the trail is noise."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "Survey A", "path": "questionnaire/survey_a"},
                {"name": "Survey B", "path": "questionnaire/survey_b"},
                {"name": "End", "path": "end"},
            ],
            "USE_BREADCRUMBS": True,
        })
        try:
            # Need empty questionnaire files so PAGE_LIST validates.
            q_dir = tmp_path / "questionnaires"
            q_dir.mkdir(exist_ok=True)
            for name in ("survey_a.json", "survey_b.json"):
                (q_dir / name).write_text(
                    json.dumps(SIMPLE_QUESTIONNAIRE), encoding="utf-8"
                )

            p = _seed_participant(app)
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = p.participantID
                sess["currentUrl"] = "end"

            response = client.get("/end")
            assert response.status_code == 200
            body = response.data.decode("utf-8")

            # Breadcrumb arrow is absent; prior page names also shouldn't
            # appear as crumbs (the surveys aren't referenced in the
            # default end.html body, so seeing "Survey A" would mean the
            # breadcrumb leaked through).
            assert "→" not in body
            assert "Survey A" not in body
            assert "Survey B" not in body
        finally:
            _teardown(app, ctx, cwd)

    def test_cold_hit_per_reason_does_not_stamp(self, tmp_path):
        """A cold /end/<reason> hit (no session) renders the default
        template anonymously without creating or stamping any row."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"path": "end/bot"},
            ],
        })
        try:
            client = app.test_client()
            response = client.get("/end/bot")
            assert response.status_code == 200
            assert app.db.session.query(app.db.Participant).count() == 0
        finally:
            _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# outgoing_url redirects (Jinja-templated)
# ---------------------------------------------------------------------------

class TestOutgoingUrlRedirect:

    def test_outgoing_url_redirects(self, tmp_path):
        """A PAGE_LIST entry with outgoing_url redirects there instead of
        rendering a template."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end/screened_out",
                 "outgoing_url": "https://example.com/screened"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end/screened_out"

            response = client.get("/end/screened_out", follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["Location"] == "https://example.com/screened"

            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.end_reason == "screened_out"
        finally:
            _teardown(app, ctx, cwd)

    def test_outgoing_url_jinja_substitution(self, tmp_path):
        """{{ participant.participantID }} inside outgoing_url is rendered
        with the participant in scope."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end/screened_out",
                 "outgoing_url": "https://example.com/?pid={{ participant.participantID }}"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end/screened_out"

            response = client.get("/end/screened_out", follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["Location"] == f"https://example.com/?pid={pid}"
        finally:
            _teardown(app, ctx, cwd)

    def test_outgoing_url_show_if_gating(self, tmp_path):
        """When two entries share the same path but different show_if,
        only the visible one is used. ``source == 'prolific'`` resolves
        against the Participant row."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end",
                 "outgoing_url": "https://prolific.example/done",
                 "show_if": "source == 'prolific'"},
                {"path": "end",
                 "outgoing_url": "https://reddit.example/done",
                 "show_if": "source == 'reddit'"},
            ],
        })
        try:
            # Prolific participant.
            p = _seed_participant(app, source="prolific")
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end"

            response = client.get("/end", follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["Location"] == "https://prolific.example/done"

            # Reddit participant.
            p2 = _seed_participant(app, source="reddit")
            pid2 = p2.participantID
            client2 = app.test_client()
            with client2.session_transaction() as sess:
                sess["participantID"] = pid2
                sess["currentUrl"] = "end"

            response2 = client2.get("/end", follow_redirects=False)
            assert response2.status_code == 302
            assert response2.headers["Location"] == "https://reddit.example/done"
        finally:
            _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# Top-level OUTGOING_URL legacy fallback
# ---------------------------------------------------------------------------

class TestLegacyOutgoingUrl:

    def test_top_level_outgoing_url_applies_to_complete(self, tmp_path):
        """A string OUTGOING_URL config redirects /end (the 'complete'
        reason) when no PAGE_LIST entry overrides it. Existing studies
        relying on the legacy form keep working."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "OUTGOING_URL": "https://legacy.example/done",
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end"

            response = client.get("/end", follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["Location"] == "https://legacy.example/done"

            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.end_reason == "complete"
        finally:
            _teardown(app, ctx, cwd)

    def test_top_level_outgoing_url_not_applied_to_non_complete(self, tmp_path):
        """Top-level OUTGOING_URL must NOT be applied for non-'complete'
        reasons — this prevents framework wire-ins (bot, quota_full, etc.)
        from inadvertently handing out the happy-path completion URL."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "OUTGOING_URL": "https://legacy.example/done",
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end/bot"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end/bot"

            response = client.get("/end/bot")
            # No redirect — falls through to template.
            assert response.status_code == 200
            assert b"Thanks for participating" in response.data

            refreshed = app.db.session.get(app.db.Participant, pid)
            assert refreshed.end_reason == "bot"
        finally:
            _teardown(app, ctx, cwd)

    def test_per_entry_outgoing_url_overrides_legacy(self, tmp_path):
        """When both a top-level OUTGOING_URL and a per-entry outgoing_url
        are set, the per-entry value wins."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "OUTGOING_URL": "https://legacy.example/done",
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end",
                 "outgoing_url": "https://per-entry.example/done"},
            ],
        })
        try:
            p = _seed_participant(app)
            pid = p.participantID
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = pid
                sess["currentUrl"] = "end"

            response = client.get("/end", follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["Location"] == "https://per-entry.example/done"
        finally:
            _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# Wire-ins
# ---------------------------------------------------------------------------

class TestBotWireIn:

    def test_bot_user_agent_redirects_to_end_bot(self, tmp_path):
        """A POST to /consent with a crawler User-Agent commits an
        isCrawler participant with end_reason='bot' and redirects to
        /end/bot without consuming a balanced slot."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "CONDITIONS": [
                {"label": "Control", "enabled": True},
                {"label": "Treatment", "enabled": True},
            ],
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            client = app.test_client()
            # Crawler User-Agent. Flask's test client respects this header
            # and CrawlerDetect's heuristics flag googlebot strings.
            response = client.post(
                "/consent",
                data={"consent": "1"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"},
                follow_redirects=False,
            )

            assert response.status_code == 302
            assert response.headers["Location"].endswith("/end/bot")

            # Exactly one participant; flagged as crawler, stamped, no
            # condition assigned. Condition stays at the column default 0
            # (same as consent_nc); excludeFromCount keeps the row out of
            # the balancer regardless.
            participants = app.db.session.query(app.db.Participant).all()
            assert len(participants) == 1
            p = participants[0]
            assert p.isCrawler is True
            assert p.end_reason == "bot"
            assert p.condition == 0
            assert p.excludeFromCount is True
        finally:
            _teardown(app, ctx, cwd)


class TestNoConsentWireIn:

    def test_decline_consent_creates_minimal_participant(self, tmp_path):
        """POST to /decline_consent creates a minimal Participant row
        (condition=None, end_reason='no_consent') and redirects to
        /end/no_consent."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "CONDITIONS": [
                {"label": "Control", "enabled": True},
                {"label": "Treatment", "enabled": True},
            ],
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            client = app.test_client()
            response = client.post("/decline_consent", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"].endswith("/end/no_consent")

            participants = app.db.session.query(app.db.Participant).all()
            assert len(participants) == 1
            p = participants[0]
            assert p.end_reason == "no_consent"
            assert p.condition == 0
            assert p.excludeFromCount is True
        finally:
            _teardown(app, ctx, cwd)

    def test_consent_form_consent_zero_routes_to_decline(self, tmp_path):
        """Defense-in-depth: posting consent=0 to /consent (bypassing the
        client-side validator) is routed through the decline path."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "CONDITIONS": [
                {"label": "Control", "enabled": True},
                {"label": "Treatment", "enabled": True},
            ],
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            client = app.test_client()
            response = client.post(
                "/consent", data={"consent": "0"}, follow_redirects=False,
            )

            assert response.status_code == 302
            assert response.headers["Location"].endswith("/end/no_consent")

            participants = app.db.session.query(app.db.Participant).all()
            assert len(participants) == 1
            assert participants[0].end_reason == "no_consent"
        finally:
            _teardown(app, ctx, cwd)


class TestQuotaFullWireIn:

    def test_quota_full_creates_participant_and_redirects(self, tmp_path):
        """When all conditions are disabled, /consent creates a minimal
        Participant with end_reason='quota_full' and redirects."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "CONDITIONS": [
                {"label": "Control", "enabled": False},
                {"label": "Treatment", "enabled": False},
            ],
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "End", "path": "end"},
            ],
        })
        try:
            client = app.test_client()
            response = client.get("/consent", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"].endswith("/end/quota_full")

            participants = app.db.session.query(app.db.Participant).all()
            assert len(participants) == 1
            p = participants[0]
            assert p.end_reason == "quota_full"
            assert p.condition == 0
            assert p.excludeFromCount is True
        finally:
            _teardown(app, ctx, cwd)


# Restored-orphan label: session recovery creates an orphan row on the
# attempting entry (``/consent`` or lazy creation commits it before
# ``/external_id`` runs, then restoration points the session at the past
# row). Labeling that orphan with ``end_reason = "session_loaded"`` lets admins
# count "this row exists because we loaded a prior session for the same
# external ID" alongside the other framework reasons, without changing
# what the participant sees.
#
# A more aggressive "block duplicates → /end/duplicate" wire-in is
# explicitly NOT implemented here: it would replace the documented
# ``ALLOW_RETAKES = False`` restore-to-/end behavior and break
# tests/tier3/test_session_recovery.py. Researchers who want that can
# still stamp ``end_reason = "duplicate"`` and redirect from custom code;
# ``/end/<reason>`` handles any reason string.

class TestRestoredOrphanLabel:

    def _seed_past_attempt(self, app, mturk_id, finished):
        """Insert a past Participant + matching SessionStore row for the
        given external ID, returning the past Participant. Used to put
        try_restore into the path where it would create an orphan."""
        from BOFS.util import utcnow_naive
        from BOFS.BOFSSession import BOFSSessionInterface

        past = app.db.Participant()
        past.externalID = mturk_id
        past.ipAddress = "127.0.0.1"
        past.userAgent = "test"
        past.condition = 1
        past.finished = finished
        past.timeStarted = utcnow_naive()
        if finished:
            past.timeEnded = utcnow_naive()
        app.db.session.add(past)
        app.db.session.commit()

        store_row = app.db.SessionStore()
        store_row.sessionID = f"past-session-{past.participantID}"
        store_row.externalID = mturk_id
        store_row.participantID = past.participantID
        store_row.data = BOFSSessionInterface.serializer.dumps({
            "currentUrl": "end" if finished else "questionnaire/survey",
            "participantID": past.participantID,
            "condition": 1,
        })
        store_row.createdOn = utcnow_naive()
        app.db.session.add(store_row)
        app.db.session.commit()
        return past

    def _app_with_external_id_flow(self, tmp_path, allow_retakes):
        """Standard app that exercises the external_id → try_restore path."""
        _write_consent_stub(tmp_path)
        q_dir = tmp_path / "questionnaires"
        if not q_dir.exists():
            q_dir.mkdir()
        # The restore path may redirect to ``questionnaire/survey``; without
        # a backing JSON file BOFS treats the PAGE_LIST entry as invalid and
        # the experiment becomes unreachable.
        (q_dir / "survey.json").write_text(
            json.dumps(SIMPLE_QUESTIONNAIRE), encoding="utf-8"
        )
        return _make_app(tmp_path, {
            "RETRIEVE_SESSIONS": True,
            "ALLOW_RETAKES": allow_retakes,
            "CONDITIONS": [
                {"label": "Control", "enabled": True},
            ],
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"name": "External", "path": "external_id"},
                {"name": "Survey", "path": "questionnaire/survey"},
                {"name": "End", "path": "end"},
            ],
        })

    def _drive_to_external_id_post(self, app, mturk_id):
        """Consent → external_id POST. Returns the client (with the orphan
        pid still in session at the moment of POST; the restore will swap
        it for the past pid)."""
        client = app.test_client()
        client.post("/consent", data={"consent": "1"})
        with client.session_transaction() as sess:
            sess["currentUrl"] = "external_id"
        response = client.post(
            "/external_id",
            data={"mTurkID": mturk_id},
            follow_redirects=False,
        )
        return client, response

    def test_orphan_labeled_when_finished_past_restored(self, tmp_path):
        """With ALLOW_RETAKES=False and a finished past attempt, the
        attempting row is labeled end_reason='session_loaded' even though the
        participant ends up restored to the past /end (documented
        behavior preserved)."""
        app, ctx, cwd = self._app_with_external_id_flow(tmp_path, allow_retakes=False)
        try:
            past = self._seed_past_attempt(app, "DUP_PID", finished=True)
            client, response = self._drive_to_external_id_post(app, "DUP_PID")

            # The restore returned the past currentUrl — behavior preserved.
            # Recovered URLs are stored relative (e.g. "end"); the route's
            # redirect call wraps them so the final Location is application-
            # relative, ending in "/end".
            assert response.status_code == 302
            assert response.headers["Location"].rstrip("/").endswith("end")

            # Now find the orphan: a participant with the right external ID
            # that is NOT the past row.
            orphans = (
                app.db.session.query(app.db.Participant)
                .filter(
                    app.db.Participant.externalID == "DUP_PID",
                    app.db.Participant.participantID != past.participantID,
                )
                .all()
            )
            assert len(orphans) == 1
            assert orphans[0].end_reason == "session_loaded"

            # Past participant is untouched (no end_reason yet — /end stamp
            # happens when the restored session lands there on the next
            # request, not here).
            refreshed_past = app.db.session.get(app.db.Participant, past.participantID)
            assert refreshed_past.finished is True
        finally:
            _teardown(app, ctx, cwd)

    def test_orphan_labeled_when_unfinished_past_resumed(self, tmp_path):
        """ALLOW_RETAKES=True + unfinished past → resume happens, orphan
        still created, label applies. Same mechanism, different reason
        for the participant being back."""
        app, ctx, cwd = self._app_with_external_id_flow(tmp_path, allow_retakes=True)
        try:
            past = self._seed_past_attempt(app, "RESUME_PID", finished=False)
            client, response = self._drive_to_external_id_post(app, "RESUME_PID")

            assert response.status_code == 302
            assert "questionnaire/survey" in response.headers["Location"]

            orphans = (
                app.db.session.query(app.db.Participant)
                .filter(
                    app.db.Participant.externalID == "RESUME_PID",
                    app.db.Participant.participantID != past.participantID,
                )
                .all()
            )
            assert len(orphans) == 1
            assert orphans[0].end_reason == "session_loaded"
        finally:
            _teardown(app, ctx, cwd)

    def test_no_orphan_when_no_recovery_happens(self, tmp_path):
        """ALLOW_RETAKES=True + finished past → finished is filtered out by
        _matching_past_participants, recovery does not run, no orphan
        exists. The current row remains the participant (no end_reason
        stamp from this flow)."""
        app, ctx, cwd = self._app_with_external_id_flow(tmp_path, allow_retakes=True)
        try:
            past = self._seed_past_attempt(app, "FRESH_PID", finished=True)
            client, response = self._drive_to_external_id_post(app, "FRESH_PID")

            # Recovery didn't fire — caller falls through to redirect_from_page.
            assert response.status_code == 302
            assert "/redirect_from_page" in response.headers["Location"]

            # The "would-be orphan" is now the legitimate current participant.
            # It should NOT carry end_reason="session_loaded" because no
            # restore ran.
            currents = (
                app.db.session.query(app.db.Participant)
                .filter(
                    app.db.Participant.externalID == "FRESH_PID",
                    app.db.Participant.participantID != past.participantID,
                )
                .all()
            )
            assert len(currents) == 1
            assert currents[0].end_reason is None
        finally:
            _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# Expression engine: reserved bare names
# ---------------------------------------------------------------------------

class TestReservedBareNames:

    def test_source_and_end_reason_resolve_to_participant_columns(self, tmp_path):
        """show_if predicates referencing `source` and `end_reason` resolve
        against the Participant row, not questionnaires. Use show_if-gated
        outgoing_url entries to exercise the resolution path through the
        real PageList machinery."""
        _write_consent_stub(tmp_path)
        app, ctx, cwd = _make_app(tmp_path, {
            "PAGE_LIST": [
                {"name": "Consent", "path": "consent"},
                {"path": "end",
                 "outgoing_url": "https://prolific.example/",
                 "show_if": "source == 'prolific'"},
                {"path": "end",
                 "outgoing_url": "https://other.example/"},
            ],
        })
        try:
            # source='prolific' → first arm.
            p1 = _seed_participant(app, source="prolific")
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["participantID"] = p1.participantID
                sess["currentUrl"] = "end"
            r1 = client.get("/end", follow_redirects=False)
            assert r1.headers["Location"] == "https://prolific.example/"

            # source=None → first arm doesn't match (None != 'prolific'),
            # falls through to the second.
            p2 = _seed_participant(app, source=None)
            client2 = app.test_client()
            with client2.session_transaction() as sess:
                sess["participantID"] = p2.participantID
                sess["currentUrl"] = "end"
            r2 = client2.get("/end", follow_redirects=False)
            assert r2.headers["Location"] == "https://other.example/"

            # source='' (empty string) → also doesn't match 'prolific'.
            p3 = _seed_participant(app, source="")
            client3 = app.test_client()
            with client3.session_transaction() as sess:
                sess["participantID"] = p3.participantID
                sess["currentUrl"] = "end"
            r3 = client3.get("/end", follow_redirects=False)
            assert r3.headers["Location"] == "https://other.example/"
        finally:
            _teardown(app, ctx, cwd)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

class TestOutgoingUrlValidation:

    def test_outgoing_url_on_non_end_path_raises(self, tmp_path):
        """outgoing_url on a non-end entry must fail at app startup with a
        clear error — guards against the "is this page redirect or
        render?" ambiguity."""
        _write_consent_stub(tmp_path)
        with pytest.raises(Exception) as excinfo:
            _make_app(tmp_path, {
                "PAGE_LIST": [
                    {"name": "Consent", "path": "consent"},
                    {"path": "questionnaire/foo",
                     "outgoing_url": "https://example.com/oops"},
                    {"name": "End", "path": "end"},
                ],
            })
        assert "outgoing_url" in str(excinfo.value)

    def test_outgoing_url_empty_string_raises(self, tmp_path):
        """An empty outgoing_url is invalid even on an end entry."""
        _write_consent_stub(tmp_path)
        with pytest.raises(Exception) as excinfo:
            _make_app(tmp_path, {
                "PAGE_LIST": [
                    {"name": "Consent", "path": "consent"},
                    {"path": "end", "outgoing_url": ""},
                ],
            })
        assert "outgoing_url" in str(excinfo.value)
