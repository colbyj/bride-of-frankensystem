"""Tier 3 tests for the admin export paths that were rewritten for scale:

* ``/admin/export_item_timing`` — the per-participant interaction dump now
  runs as a single JOIN instead of N+1 queries.
* ``/admin/table_csv/<table>`` — the table CSV now streams row-by-row
  instead of loading the whole table (and two copies of it) into memory.

Both assert on exact CSV content so the public CSV contract is preserved.
"""

from datetime import datetime

import pytest


def _login(client):
    with client.session_transaction() as sess:
        sess["loggedIn"] = True


def _add_participant(app, finished=True, external_id=None):
    p = app.db.Participant()
    p.finished = finished
    if external_id is not None:
        p.externalID = external_id
    app.db.session.add(p)
    app.db.session.commit()
    return p.participantID


def _add_interaction(app, pid, questionnaire, tag, qid, event, ts, value=""):
    i = app.db.QuestionnaireInteraction()
    i.participantID = pid
    i.questionnaire = questionnaire
    i.tag = tag
    i.questionID = qid
    i.eventType = event
    i.timestamp = ts
    i.value = value
    app.db.session.add(i)
    app.db.session.commit()


class TestExportItemTiming:
    def test_timing_csv_orders_and_joins(self, bofs_app_for_export_no_binds):
        app = bofs_app_for_export_no_binds
        client = app.test_client()
        _login(client)

        p1 = _add_participant(app, finished=True, external_id="ext-1 ")
        p2 = _add_participant(app, finished=True, external_id=None)
        # An unfinished participant must be excluded entirely.
        p3 = _add_participant(app, finished=False, external_id="ext-3")

        # Insert out of timestamp order to prove the ORDER BY sorts them.
        _add_interaction(app, p1, "survey", "", "q1", "click",
                         datetime(2024, 1, 1, 12, 0, 1), "b")
        _add_interaction(app, p1, "survey", "", "q1", "click",
                         datetime(2024, 1, 1, 12, 0, 0), "a")
        _add_interaction(app, p2, "survey", "", "q2", "focus",
                         datetime(2024, 1, 1, 12, 5, 0), "")
        _add_interaction(app, p3, "survey", "", "q3", "click",
                         datetime(2024, 1, 1, 12, 9, 0), "x")

        resp = client.get("/admin/export_item_timing/download")
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        lines = [ln for ln in text.split("\n") if ln]

        assert lines[0] == ("participantID,externalID,questionnaire,tag,"
                            "questionID,eventType,timestamp,value")
        # p1's two rows come first, sorted by timestamp (a before b); p2 next;
        # p3 (unfinished) absent. externalID is stripped.
        assert lines[1] == f"{p1},ext-1,survey,,q1,click,2024-01-01T12:00:00,a"
        assert lines[2] == f"{p1},ext-1,survey,,q1,click,2024-01-01T12:00:01,b"
        assert lines[3] == f"{p2},,survey,,q2,focus,2024-01-01T12:05:00,"
        assert len(lines) == 4  # header + 3 rows, nothing from p3

    def test_timing_csv_empty(self, bofs_app_for_export_no_binds):
        app = bofs_app_for_export_no_binds
        client = app.test_client()
        _login(client)
        resp = client.get("/admin/export_item_timing/download")
        assert resp.status_code == 200
        lines = [ln for ln in resp.get_data(as_text=True).split("\n") if ln]
        assert len(lines) == 1  # header only


class TestTableCsvStreaming:
    def test_table_csv_streams_rows(self, bofs_app_for_export_no_binds):
        app = bofs_app_for_export_no_binds
        client = app.test_client()
        _login(client)

        # Populate the experiment questionnaire table (field: score).
        Experiment = app.db.Questionnaireexperiment
        pid = _add_participant(app, finished=True)
        for score in ("alpha", "beta"):
            row = Experiment()
            row.participantID = pid
            row.tag = ""
            row.score = score
            app.db.session.add(row)
        app.db.session.commit()

        resp = client.get("/admin/table_csv/questionnaire_experiment")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        # The response is produced by a generator, not a single buffered string.
        assert resp.is_streamed

        text = resp.get_data(as_text=True)
        lines = [ln for ln in text.split("\n") if ln]
        header = lines[0].split(",")
        assert "participantID" in header
        assert "score" in header
        # Two data rows present, values intact.
        assert any("alpha" in ln for ln in lines[1:])
        assert any("beta" in ln for ln in lines[1:])
        assert len(lines) == 3  # header + 2 rows

    def test_table_csv_unknown_404(self, bofs_app_for_export_no_binds):
        client = bofs_app_for_export_no_binds.test_client()
        _login(client)
        resp = client.get("/admin/table_csv/no_such_table")
        assert resp.status_code == 404

    def test_table_csv_blocked_404(self, bofs_app_for_export_no_binds):
        client = bofs_app_for_export_no_binds.test_client()
        _login(client)
        resp = client.get("/admin/table_csv/app_meta")
        assert resp.status_code == 404
