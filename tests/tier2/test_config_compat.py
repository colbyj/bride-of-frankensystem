"""Tier 2 tests for config-key backward compatibility.

Ensures the deprecated ``LOG_GRID_CLICKS`` key is mapped to its replacement
``LOG_QUESTIONNAIRE_INTERACTIONS`` at app-creation time.
"""

import os

import toml


def _build_app(tmp_path, config_data):
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")
    (tmp_path / "questionnaires").mkdir()
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    original_cwd = os.getcwd()
    try:
        from BOFS.create_app import create_app
        app = create_app(str(tmp_path), str(config_path), debug=True)
    finally:
        os.chdir(original_cwd)
    return app


_BASE_CONFIG = {
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "SECRET_KEY": "test-secret-key",
    "TITLE": "Test Experiment",
    "ADMIN_PASSWORD": "test",
    "USE_ADMIN": False,
    "BRUTE_FORCE_PROTECTION": False,
    "PAGE_LIST": [
        {"name": "Consent", "path": "consent"},
        {"name": "End", "path": "end"},
    ],
}


def test_log_grid_clicks_alias_maps_to_new_key(tmp_path):
    config = dict(_BASE_CONFIG)
    config["LOG_GRID_CLICKS"] = True
    app = _build_app(tmp_path, config)
    assert app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] is True


def test_new_key_takes_precedence(tmp_path):
    config = dict(_BASE_CONFIG)
    config["LOG_GRID_CLICKS"] = True
    config["LOG_QUESTIONNAIRE_INTERACTIONS"] = False
    app = _build_app(tmp_path, config)
    assert app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] is False


def test_default_when_neither_key_present(tmp_path):
    app = _build_app(tmp_path, dict(_BASE_CONFIG))
    assert app.config["LOG_QUESTIONNAIRE_INTERACTIONS"] is False
