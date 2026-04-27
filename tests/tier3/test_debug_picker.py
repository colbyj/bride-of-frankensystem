"""Tier 3 integration tests for the debug-mode condition picker.

When BOFS is run with -d, /consent and /assign_condition redirect to
/debug_pick_condition instead of running the balancer automatically.
"""

import json
import os

import pytest
import toml


@pytest.fixture
def bofs_app_debug(tmp_path):
    """BOFS app started with debug=True. PAGE_LIST: consent → end."""
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Debug Picker Test",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
            {"label": "Off", "enabled": False},
        ],
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=True)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


class TestDebugPicker:
    def test_consent_redirects_to_picker_in_debug(self, bofs_app_debug):
        client = bofs_app_debug.test_client()
        response = client.post("/consent", follow_redirects=False)

        assert response.status_code == 302
        assert "/debug_pick_condition" in response.location

    def test_picker_leaves_condition_zero_until_chosen(self, bofs_app_debug):
        app = bofs_app_debug
        client = app.test_client()
        client.post("/consent", follow_redirects=False)

        p = app.db.session.query(app.db.Participant).first()
        assert p is not None
        assert p.condition == 0

    def test_picker_get_renders(self, bofs_app_debug):
        client = bofs_app_debug.test_client()
        client.post("/consent", follow_redirects=False)
        response = client.get("/debug_pick_condition")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # All three condition labels appear, including the disabled one.
        assert "Control" in body
        assert "Treatment" in body
        assert "Off" in body
        # The balancer's pick is annotated inline.
        assert "would be assigned automatically" in body

    def test_picker_post_assigns_chosen_condition(self, bofs_app_debug):
        app = bofs_app_debug
        client = app.test_client()
        client.post("/consent", follow_redirects=False)

        # Pick condition 2 explicitly (not what the balancer would pick first).
        response = client.post(
            "/debug_pick_condition",
            data={"condition": "2"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/redirect_next_page" in response.location

        p = app.db.session.query(app.db.Participant).first()
        assert p.condition == 2

        with client.session_transaction() as sess:
            assert sess["condition"] == 2

    def test_picker_rejects_disabled_condition(self, bofs_app_debug):
        app = bofs_app_debug
        client = app.test_client()
        client.post("/consent", follow_redirects=False)

        response = client.post(
            "/debug_pick_condition",
            data={"condition": "3"},  # "Off" is disabled
            follow_redirects=False,
        )
        assert response.status_code == 400

        p = app.db.session.query(app.db.Participant).first()
        assert p.condition == 0  # unchanged

    def test_picker_rejects_out_of_range(self, bofs_app_debug):
        client = bofs_app_debug.test_client()
        client.post("/consent", follow_redirects=False)

        for bad in ("0", "99", "abc"):
            response = client.post(
                "/debug_pick_condition",
                data={"condition": bad},
                follow_redirects=False,
            )
            assert response.status_code == 400, f"value {bad!r}"

    def test_picker_404_when_not_in_debug_mode(self, tmp_path):
        """Without debug mode the picker route must not be reachable."""
        (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")
        config_data = {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret-key",
            "TITLE": "No Debug",
            "ADMIN_PASSWORD": "test",
            "USE_ADMIN": False,
            "CONDITIONS": [
                {"label": "A", "enabled": True},
                {"label": "B", "enabled": True},
            ],
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
        try:
            client = app.test_client()
            client.post("/consent", follow_redirects=False)
            response = client.get("/debug_pick_condition")
            assert response.status_code == 404
        finally:
            app.db.drop_all()
            ctx.pop()
            os.chdir(original_cwd)
