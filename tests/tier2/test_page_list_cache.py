"""Tier 2 tests for the request-scoped ``flat_page_list`` cache.

The cache lives on ``flask.g`` and is invalidated on SQLAlchemy
``after_commit`` so a write-then-read within one request stays correct.
These tests need a request context (the cache no-ops without one), so they
use the ``bofs_app`` fixture and push a ``test_request_context``.
"""

import os

import toml

from BOFS.PageList import _flat_page_list_cache, invalidate_flat_page_list_cache


def _make_show_if_app(tmp_path):
    """App whose PAGE_LIST has a page gated on ``source == 'prolific'`` — a
    show_if that resolves against the live Participant row, so its visibility
    flips when the participant's source is committed."""
    config = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Prolific only", "path": "instructions/prolific",
             "show_if": "source == 'prolific'"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config), encoding="utf-8")
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    cwd = os.getcwd()
    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=True)
    ctx = app.app_context()
    ctx.push()
    return app, ctx, cwd


class TestFlatPageListCache:
    def test_second_call_is_served_from_cache(self, bofs_app):
        """Tampering with the cached value and seeing the next call return it
        proves the second call short-circuited rather than rebuilt."""
        with bofs_app.test_request_context("/"):
            pl = bofs_app.page_list
            pl.flat_page_list()
            cache = _flat_page_list_cache()
            (key,) = cache.keys()
            cache[key] = [{"path": "sentinel"}]
            second = pl.flat_page_list()
            assert [e["path"] for e in second] == ["sentinel"]

    def test_distinct_keys_cached_separately(self, bofs_app):
        """Different (condition, hide_unresolved) inputs are cached under
        separate keys and don't collide."""
        with bofs_app.test_request_context("/"):
            pl = bofs_app.page_list
            a = pl.flat_page_list(condition=1)
            c = pl.flat_page_list(condition=1, hide_unresolved=True)
            cache = _flat_page_list_cache()
            # participant_id resolves to None (no participantID in session).
            assert (1, None, False) in cache
            assert (1, None, True) in cache
            assert [e["path"] for e in a] == [e["path"] for e in cache[(1, None, False)]]
            assert a is not c  # different cache key, distinct results

    def test_commit_invalidates_cache(self, bofs_app):
        """A DB commit clears the cache so the next call rebuilds — this is
        what keeps route_end's stamp-then-resolve correct."""
        with bofs_app.test_request_context("/"):
            pl = bofs_app.page_list
            first = pl.flat_page_list()

            # A real write + commit fires the after_commit listener.
            p = bofs_app.db.Participant()
            bofs_app.db.session.add(p)
            bofs_app.db.session.commit()

            second = pl.flat_page_list()
            assert first is not second
            # Same content, freshly built.
            assert [e["path"] for e in first] == [e["path"] for e in second]

    def test_explicit_invalidation(self, bofs_app):
        with bofs_app.test_request_context("/"):
            pl = bofs_app.page_list
            first = pl.flat_page_list()
            invalidate_flat_page_list_cache()
            second = pl.flat_page_list()
            assert first is not second

    def test_no_request_context_does_not_cache(self, bofs_app):
        """Outside a request there is no ``g`` to cache on, so each call
        recomputes (and the cache accessor reports unavailable)."""
        # bofs_app pushes only an app context, not a request context.
        assert _flat_page_list_cache() is None
        pl = bofs_app.page_list
        first = pl.flat_page_list(participant_id=None)
        second = pl.flat_page_list(participant_id=None)
        assert first is not second

    def test_mutating_returned_list_does_not_poison_cache(self, bofs_app):
        """Each call hands back its own list — appending to one result must
        not change what a later call sees (the pre-cache invariant)."""
        with bofs_app.test_request_context("/"):
            pl = bofs_app.page_list
            first = pl.flat_page_list()
            n = len(first)
            first.append({"path": "injected"})
            second = pl.flat_page_list()
            assert len(second) == n
            assert all(e.get("path") != "injected" for e in second)


class TestCacheReflectsCommittedShowIf:
    """The whole point of after_commit invalidation: a show_if whose value
    changes when data is committed must be reflected on the next read."""

    def test_committed_source_flips_page_visibility(self, tmp_path):
        app, ctx, cwd = _make_show_if_app(tmp_path)
        try:
            from BOFS.util import utcnow_naive
            p = app.db.Participant()
            p.ipAddress = "127.0.0.1"
            p.userAgent = "test"
            p.condition = 0
            p.timeStarted = utcnow_naive()
            app.db.session.add(p)
            app.db.session.commit()

            with app.test_request_context("/"):
                from flask import session
                session["participantID"] = p.participantID

                # source is unset → "source == 'prolific'" is false → hidden.
                paths = [e["path"] for e in app.page_list.flat_page_list()]
                assert "instructions/prolific" not in paths

                # Commit the gating value; after_commit must drop the cache.
                p.source = "prolific"
                app.db.session.commit()

                paths = [e["path"] for e in app.page_list.flat_page_list()]
                assert "instructions/prolific" in paths
        finally:
            app.db.drop_all()
            ctx.pop()
            os.chdir(cwd)
