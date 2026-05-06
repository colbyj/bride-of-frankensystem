"""Tier 3 integration tests for the image_click question type.

End-to-end coverage: questionnaire JSON → DB schema → form submission →
stored row → re-render with prior values.
"""

import json
import os

import pytest
import toml

from tests.conftest import create_participant_via_consent, submit_questionnaire_data


IMAGE_CLICK_QUESTIONNAIRE = {
    "title": "Click Test",
    "instructions": "",
    "questions": [
        {
            "questiontype": "image_click",
            "id": "single_target",
            "instructions": "Click the centre.",
            "image_src": "/static/marker.png",
            "required": True,
        },
        {
            "questiontype": "image_click",
            "id": "many_spots",
            "instructions": "Click on every dot.",
            "image_src": "/static/marker.png",
            "max_clicks": 3,
        },
    ],
}


@pytest.fixture
def bofs_app_image_click(tmp_path):
    """A BOFS app whose page list includes an image_click questionnaire."""
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "click.json").write_text(
        json.dumps(IMAGE_CLICK_QUESTIONNAIRE), encoding="utf-8"
    )
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Click", "path": "questionnaire/click"},
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


# ===========================================================================
# Schema
# ===========================================================================

class TestImageClickSchema:
    def test_single_click_creates_xy_float_columns(self, bofs_app_image_click):
        """Default (max_clicks=1) yields {id}_x and {id}_y FLOAT columns."""
        q = bofs_app_image_click.questionnaires["click"]
        cols = {c.name: c for c in q.db_class.__table__.columns}
        assert "single_target_x" in cols
        assert "single_target_y" in cols
        assert "single_target" not in cols
        # Float on SQLAlchemy maps to NUMERIC/REAL on SQLite
        assert "FLOAT" in str(cols["single_target_x"].type).upper() \
               or "NUMERIC" in str(cols["single_target_x"].type).upper() \
               or "REAL"  in str(cols["single_target_x"].type).upper()

    def test_multi_click_creates_single_text_column(self, bofs_app_image_click):
        """max_clicks > 1 yields one TEXT column at {id}, no _x/_y columns."""
        q = bofs_app_image_click.questionnaires["click"]
        cols = {c.name: c for c in q.db_class.__table__.columns}
        assert "many_spots" in cols
        assert "many_spots_x" not in cols
        assert "many_spots_y" not in cols
        assert "TEXT" in str(cols["many_spots"].type).upper()


# ===========================================================================
# Submission
# ===========================================================================

class TestImageClickSubmission:
    def test_single_click_values_persist_as_floats(self, bofs_app_image_click):
        app = bofs_app_image_click
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "click", data_dict={
            "single_target_x": "123.45",
            "single_target_y": "67.89",
            "many_spots": json.dumps([{"x": 10.0, "y": 20.0}]),
        })

        q = app.questionnaires["click"]
        rows = q.fetch_all_data()
        assert len(rows) == 1
        row = rows[0]
        assert row.single_target_x == pytest.approx(123.45)
        assert row.single_target_y == pytest.approx(67.89)

    def test_multi_click_value_persists_as_json_string(self, bofs_app_image_click):
        app = bofs_app_image_click
        client = app.test_client()
        create_participant_via_consent(client, app)

        points = [{"x": 10.5, "y": 20.5}, {"x": 30.0, "y": 40.0}]
        submit_questionnaire_data(client, "click", data_dict={
            "single_target_x": "1.0", "single_target_y": "2.0",
            "many_spots": json.dumps(points),
        })

        row = app.questionnaires["click"].fetch_all_data()[0]
        assert isinstance(row.many_spots, str)
        assert json.loads(row.many_spots) == points

    def test_unsubmitted_optional_field_uses_default(self, bofs_app_image_click):
        """When the participant submits without clicking the multi-click image
        (its hidden input is `disabled` and so omitted from the form), the row
        gets the column's default ('') rather than crashing."""
        app = bofs_app_image_click
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "click", data_dict={
            "single_target_x": "5.0", "single_target_y": "6.0",
            # many_spots intentionally omitted
        })

        row = app.questionnaires["click"].fetch_all_data()[0]
        assert row.many_spots == ""


# ===========================================================================
# Re-entry / prior-value rendering
# ===========================================================================

class TestImageClickPriorValues:
    def test_resubmit_overwrites_single_click_xy(self, bofs_app_image_click):
        """A second submit with the same tag updates the prior x,y in place."""
        app = bofs_app_image_click
        client = app.test_client()
        create_participant_via_consent(client, app)

        # First submission
        submit_questionnaire_data(client, "click", data_dict={
            "single_target_x": "10", "single_target_y": "20",
            "many_spots": "[]",
        })

        # Navigate back via session to allow resubmit of the same questionnaire
        with client.session_transaction() as sess:
            sess["currentUrl"] = "questionnaire/click"

        submit_questionnaire_data(client, "click", data_dict={
            "single_target_x": "100", "single_target_y": "200",
            "many_spots": "[]",
        })

        rows = app.questionnaires["click"].fetch_all_data()
        assert len(rows) == 1
        assert rows[0].single_target_x == pytest.approx(100.0)
        assert rows[0].single_target_y == pytest.approx(200.0)

    def test_render_after_submit_includes_prior_xy_in_html(
            self, bofs_app_image_click):
        """After submitting, GETing the questionnaire restores prior x/y as
        the value attributes on the hidden inputs (the template reads
        `prior_x`/`prior_y` injected by ParticipantQuestionnaireService)."""
        app = bofs_app_image_click
        client = app.test_client()
        create_participant_via_consent(client, app)

        submit_questionnaire_data(client, "click", data_dict={
            "single_target_x": "42.5", "single_target_y": "99.25",
            "many_spots": json.dumps([{"x": 7.0, "y": 8.0}]),
        })

        with client.session_transaction() as sess:
            sess["currentUrl"] = "questionnaire/click"

        resp = client.get("/questionnaire/click")
        html = resp.get_data(as_text=True)
        # Single-click prior values surface as `value="..."` on the _x/_y
        # hidden inputs (inputs are NOT disabled when a prior value exists).
        assert 'name="single_target_x"' in html
        assert 'value="42.5"' in html
        assert 'name="single_target_y"' in html
        assert 'value="99.25"' in html
        # Multi-click prior value surfaces as `value="..."` on the points
        # hidden input (JSON-escaped).
        assert 'name="many_spots"' in html
        assert '7.0' in html and '8.0' in html
