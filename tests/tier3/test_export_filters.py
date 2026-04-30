"""Tier 3 tests for export filter parsing (pins the bool-parsing bug fix).

Tests the /admin/export endpoint with all combinations of includeUnfinished
and includeExcluded, including the string 'false' case that was previously
mis-parsed as truthy.
"""

import json
import os

import pytest
import toml
from datetime import datetime


# ===========================================================================
# Fixture — same as bofs_app_with_questionnaires but with admin enabled
# ===========================================================================

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
    """
    BOFS app with admin panel enabled and questionnaires configured.
    Suitable for testing admin routes.
    """
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
        # USE_ADMIN defaults to True when omitted — admin blueprint is registered
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


# ===========================================================================
# Helpers
# ===========================================================================

def _seed_participants(app):
    """
    Seed 4 participants covering all combinations of finished/excluded:
      P1: finished=True,  excludeFromCount=False  (finished, included)
      P2: finished=False, excludeFromCount=False  (unfinished, included)
      P3: finished=True,  excludeFromCount=True   (finished, excluded)
      P4: finished=False, excludeFromCount=True   (unfinished, excluded)
    Returns (p1, p2, p3, p4).
    """
    def make(finished, excluded):
        p = app.db.Participant()
        p.mTurkID = ""
        p.ipAddress = "127.0.0.1"
        p.userAgent = "test"
        p.condition = 1
        p.finished = finished
        p.excludeFromCount = excluded
        p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        p.timeEnded = datetime(2024, 1, 1, 12, 5, 0) if finished else None
        app.db.session.add(p)

    make(True, False)   # P1
    make(False, False)  # P2
    make(True, True)    # P3
    make(False, True)   # P4
    app.db.session.commit()


def _get_export(client, **params):
    """GET /admin/export/download (CSV) with the given query params."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/admin/export/download?{query}" if query else "/admin/export/download"
    return client.get(url)


def _row_count(response):
    """Count data rows in the CSV response (excludes header row)."""
    text = response.data.decode("utf-8")
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    # First line is header
    return len(lines) - 1


def _admin_client(app):
    """Return a test_client with the admin session flag set."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['loggedIn'] = True
    return client


# ===========================================================================
# Filter combination tests
# ===========================================================================

class TestExportFilters:
    """Pin the behaviour of each includeUnfinished × includeExcluded combination."""

    def test_case1_finished_included_only(self, bofs_app_with_admin):
        """includeUnfinished=false, includeExcluded=false → only P1 (1 participant)."""
        app = bofs_app_with_admin
        _seed_participants(app)
        client = _admin_client(app)

        resp = _get_export(client, includeUnfinished='false', includeExcluded='false')
        assert resp.status_code == 200
        assert _row_count(resp) == 1

    def test_case2_unfinished_included_no_excluded(self, bofs_app_with_admin):
        """includeUnfinished=true, includeExcluded=false → P1 + P2 (2 participants)."""
        app = bofs_app_with_admin
        _seed_participants(app)
        client = _admin_client(app)

        resp = _get_export(client, includeUnfinished='true', includeExcluded='false')
        assert resp.status_code == 200
        assert _row_count(resp) == 2

    def test_case3_finished_only_with_excluded(self, bofs_app_with_admin):
        """includeUnfinished=false, includeExcluded=true → only finished, all excluded states (P1 + P3)."""
        app = bofs_app_with_admin
        _seed_participants(app)
        client = _admin_client(app)

        resp = _get_export(client, includeUnfinished='false', includeExcluded='true')
        assert resp.status_code == 200
        assert _row_count(resp) == 2  # P1 (finished, included) + P3 (finished, excluded)

    def test_case4_both_true_yields_no_filter(self, bofs_app_with_admin):
        """includeUnfinished=true, includeExcluded=true → no filter, all 4 participants."""
        app = bofs_app_with_admin
        _seed_participants(app)
        client = _admin_client(app)

        resp = _get_export(client, includeUnfinished='true', includeExcluded='true')
        assert resp.status_code == 200
        assert _row_count(resp) == 4  # All 4 participants

    # ------------------------------------------------------------------
    # Bug-specific cases: string 'FALSE' / 'False' must NOT be truthy
    # ------------------------------------------------------------------

    def test_case5_uppercase_false_matches_case1(self, bofs_app_with_admin):
        """includeUnfinished=FALSE, includeExcluded=FALSE (uppercase) → same as case 1."""
        app = bofs_app_with_admin
        _seed_participants(app)
        client = _admin_client(app)

        resp = _get_export(client, includeUnfinished='FALSE', includeExcluded='FALSE')
        assert resp.status_code == 200
        assert _row_count(resp) == 1

    def test_case6_only_include_unfinished_set(self, bofs_app_with_admin):
        """includeUnfinished=true with no includeExcluded → absent param uses default (False).

        With includeUnfinished=true and includeExcluded defaulting to False,
        the filter should be Path A: non-excluded participants only (P1 + P2).
        """
        app = bofs_app_with_admin
        _seed_participants(app)
        client = _admin_client(app)

        resp = _get_export(client, includeUnfinished='true')
        assert resp.status_code == 200
        assert _row_count(resp) == 2

    # ------------------------------------------------------------------
    # NaN handling: missing rows from outer-joined questionnaires must
    # render as empty cells, not the string "NaN".
    # ------------------------------------------------------------------

    def test_export_csv_no_literal_nan(self, bofs_app_with_admin):
        """A participant who has no row in a joined questionnaire (e.g. their
        flow branched away) produces NaN cells in the underlying DataFrame.
        The CSV must render those as empty strings, never as the literal
        string "NaN" or "nan"."""
        app = bofs_app_with_admin

        # P1 has no questionnaire/survey row at all — so all of survey's
        # columns will be NaN in the outer-joined export.
        p = app.db.Participant()
        p.mTurkID = ""
        p.ipAddress = "127.0.0.1"
        p.userAgent = "test"
        p.condition = 1
        p.finished = True
        p.excludeFromCount = False
        p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        p.timeEnded = datetime(2024, 1, 1, 12, 5, 0)
        app.db.session.add(p)
        app.db.session.commit()

        client = _admin_client(app)
        resp = _get_export(client, includeUnfinished='true')
        assert resp.status_code == 200
        text = resp.data.decode('utf-8')
        # Avoid false positives by splitting into cells and checking values.
        for line in text.splitlines()[1:]:  # skip header
            cells = line.split(',')
            for cell in cells:
                assert cell.strip() not in ('NaN', 'nan'), (
                    f"export contains literal NaN cell: {cell!r} in line {line!r}"
                )
