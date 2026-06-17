"""Tier 3 tests for the admin Preview Results routes.

Exercises the real admin routes end-to-end (routing + template rendering) so
that the per-field detail page, the overview, and the legacy boxplot redirect
are all wired up correctly:
  * /admin/results              — overview (stats table + counts table)
  * /admin/results/<field>      — per-field boxplot (continuous) or histogram
"""

import json
import os

import pytest
import toml
from datetime import datetime


SURVEY_QUESTIONNAIRE_FULL = {
    "title": "Test Survey",
    "instructions": "Answer all questions.",
    "questions": [
        {"questiontype": "field", "instructions": "Enter name", "id": "name"},
        {
            "questiontype": "slider",
            "instructions": "Rate",
            "id": "rating",
            "left": "Low",
            "right": "High",
        },
        {"questiontype": "num_field", "instructions": "Enter age", "id": "age"},
        {
            "questiontype": "radiogrid",
            "id": "grid",
            "instructions": "Rate items",
            "labels": ["1", "2", "3", "4", "5"],
            "q_text": [
                {"id": "g1_q1", "text": "Item one"},
                {"id": "g1_q2", "text": "Item two"},
            ],
        },
    ],
    "participant_calculations": {
        "grid_total": "g1_q1 + g1_q2",
    },
}


@pytest.fixture
def bofs_app_with_admin(tmp_path):
    """BOFS app with the admin panel enabled and the survey questionnaire."""
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "survey.json").write_text(
        json.dumps(SURVEY_QUESTIONNAIRE_FULL), encoding="utf-8"
    )
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "BRUTE_FORCE_PROTECTION": False,
        "GENERATE_COMPLETION_CODE": True,
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Survey", "path": "questionnaire/survey"},
            {"name": "Survey", "path": "questionnaire/survey/before"},
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
    app.db.create_all()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


def _admin_client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['loggedIn'] = True
    return client


def _seed(app, condition, name, rating, age):
    """Seed one finished participant plus a survey response (tag '')."""
    p = app.db.Participant()
    p.mTurkID = ""
    p.ipAddress = "127.0.0.1"
    p.userAgent = "test"
    p.condition = condition
    p.finished = True
    p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
    p.timeEnded = datetime(2024, 1, 1, 12, 5, 0)
    app.db.session.add(p)
    app.db.session.commit()

    q = app.questionnaires["survey"]
    record = q.db_class()
    record.participantID = p.participantID
    record.tag = ""
    record.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
    record.timeEnded = datetime(2024, 1, 1, 12, 1, 0)
    record.name = name
    record.rating = rating
    record.age = age
    record.g1_q1 = 3
    record.g1_q2 = 5
    app.db.session.add(record)
    app.db.session.commit()
    return p


def test_overview_lists_both_kinds_of_field(bofs_app_with_admin):
    app = bofs_app_with_admin
    _seed(app, 1, "Robin", 4, 30)
    _seed(app, 2, "Sky", 5, 31)
    client = _admin_client(app)

    resp = client.get("/admin/results")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # Continuous field (slider) appears under summary statistics with a link
    # into its per-field page; free-text field appears under response counts.
    assert "Summary Statistics" in body
    assert "Response Counts" in body
    assert "/admin/results/survey_rating" in body
    assert "/admin/results/survey_name" in body


def test_continuous_field_page_renders_boxplot(bofs_app_with_admin):
    app = bofs_app_with_admin
    _seed(app, 1, "Robin", 4, 30)
    _seed(app, 2, "Sky", 5, 31)
    client = _admin_client(app)

    resp = client.get("/admin/results/survey_rating")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert '"type": "box"' in body or "'type': 'box'" in body or "boxmode" in body


def test_categorical_field_page_renders_histogram_with_values(bofs_app_with_admin):
    app = bofs_app_with_admin
    _seed(app, 1, "Robin", 4, 30)
    _seed(app, 2, "Sky", 5, 31)
    client = _admin_client(app)

    resp = client.get("/admin/results/survey_name")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # The free-text values reach the page (as histogram categories / table rows).
    assert "Robin" in body
    assert "Sky" in body


def test_unknown_field_404s(bofs_app_with_admin):
    app = bofs_app_with_admin
    _seed(app, 1, "Robin", 4, 30)
    client = _admin_client(app)

    resp = client.get("/admin/results/not_a_real_field")
    assert resp.status_code == 404
