"""Tier 2 tests for the per-bind admin export pipeline.

The primary user-visible contract:

* A study with no ``SQLALCHEMY_BINDS`` and no ``database`` field on any JSON
  must produce an export CSV byte-identical to today.
* A study using a non-default bind must expose a separate download
  endpoint per bind, with ``participantID`` as the join key.
"""

import io

import pytest

from BOFS.services.data_export import Results


def _make_finished_participant(app, finished=True):
    p = app.db.Participant()
    p.finished = finished
    app.db.session.add(p)
    app.db.session.commit()
    return p


def _submit_default_questionnaire(app, participant, score):
    QClass = app.questionnaires["experiment"].db_class
    row = QClass()
    row.participantID = participant.participantID
    row.tag = ""
    row.score = score
    app.db.session.add(row)
    app.db.session.commit()


def _submit_pii_questionnaire(app, participant, email):
    QClass = app.questionnaires["contact"].db_class
    row = QClass()
    row.participantID = participant.participantID
    row.tag = ""
    row.email = email
    app.db.session.add(row)
    app.db.session.commit()


class TestExportNoBindsRegression:
    """No SQLALCHEMY_BINDS and no ``database`` field anywhere → the export
    must look exactly like it did before the per-bind work."""

    def test_single_csv_contains_all_columns(self, bofs_app_for_export_no_binds):
        app = bofs_app_for_export_no_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        QClass = app.questionnaires["contact"].db_class
        row = QClass()
        row.participantID = p.participantID
        row.tag = ""
        row.email = "x@example.com"
        app.db.session.add(row)
        app.db.session.commit()

        results = Results()
        csv_text = results.build_export_csv()

        # Header line contains both questionnaires' columns
        header = csv_text.splitlines()[0]
        assert "experiment_score" in header
        assert "contact_email" in header
        # Standard participant columns still lead the export
        assert header.split(",")[:3] == ["participantID", "externalID", "source"]

    def test_no_binds_means_column_list_by_bind_only_has_default(
        self, bofs_app_for_export_no_binds
    ):
        app = bofs_app_for_export_no_binds
        _make_finished_participant(app)
        results = Results()
        # Without SQLALCHEMY_BINDS, no entry for any non-default bind appears
        assert set(results.column_list_by_bind.keys()) == {None}

    def test_no_binds_download_keeps_merged_csv(self, bofs_app_for_export_no_binds):
        """Regression guard: when no binds are configured, the default
        download endpoint must still emit a single CSV with every
        questionnaire's columns (pre-per-bind behaviour)."""
        app = bofs_app_for_export_no_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        QClass = app.questionnaires["contact"].db_class
        row = QClass()
        row.participantID = p.participantID
        row.tag = ""
        row.email = "x@example.com"
        app.db.session.add(row)
        app.db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export/download")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Both questionnaires' columns appear in the single merged CSV.
        assert "experiment_score" in body
        assert "contact_email" in body


class TestExportWithBinds:
    def test_default_bind_csv_excludes_pii_columns(
        self, bofs_app_for_export_with_binds
    ):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        results = Results()
        default_csv = results.build_export_csv_for_bind(None)

        header = default_csv.splitlines()[0]
        assert "experiment_score" in header
        # PII column must not leak into the default-bind CSV — that's the
        # whole point of the bind separation.
        assert "contact_email" not in header

    def test_pii_csv_has_only_pii_columns(self, bofs_app_for_export_with_binds):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        results = Results()
        pii_csv = results.build_export_csv_for_bind("pii")

        header = pii_csv.splitlines()[0].split(",")
        # Both join keys lead the PII CSV so the file is recognisable on
        # its own (externalID identifies the participant outside the
        # framework — MTurk/Prolific ID, etc.) and joinable to the
        # default-bind export (via participantID).
        assert header[0] == "participantID"
        assert header[1] == "externalID"
        assert "contact_email" in header
        # No experiment data — that's the whole point of the bind.
        assert "experiment_score" not in header
        # No other participant columns either; just the join keys.
        assert "condition" not in header
        assert "source" not in header

    def test_pii_csv_joinable_on_participantID(self, bofs_app_for_export_with_binds):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        results = Results()
        default_csv = results.build_export_csv_for_bind(None)
        pii_csv = results.build_export_csv_for_bind("pii")

        default_rows = list(io.StringIO(default_csv).readlines())
        pii_rows = list(io.StringIO(pii_csv).readlines())

        # Header + one data row in each
        assert len(default_rows) == 2
        assert len(pii_rows) == 2

        default_pid = default_rows[1].split(",")[0]
        pii_pid = pii_rows[1].split(",")[0]
        assert default_pid == pii_pid == str(p.participantID)

    def test_admin_download_default_endpoint_excludes_pii(
        self, bofs_app_for_export_with_binds
    ):
        """When binds are configured, ``/admin/export/download`` must NOT
        include PII / cross-bind columns. Researchers download each bind
        separately so the privacy boundary holds even for someone who
        only ever hits the default endpoint."""
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export/download")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        body = resp.data.decode("utf-8")
        assert "experiment_score" in body
        assert "contact_email" not in body

    def test_admin_download_pii_endpoint(self, bofs_app_for_export_with_binds):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export/download/pii")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        body = resp.data.decode("utf-8")
        assert "contact_email" in body
        assert "experiment_score" not in body
        # Filename includes the bind name
        assert "export_pii_" in resp.headers["Content-Disposition"]

    def test_admin_download_unknown_bind_404(self, bofs_app_for_export_with_binds):
        app = bofs_app_for_export_with_binds
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export/download/nonexistent")
        assert resp.status_code == 404


class TestExportPreviewAndNavbar:
    """The admin /admin/export preview is also per-bind, not a merged
    view. Selecting a bind via ?bind=NAME restricts the preview and the
    download button on that page. The navbar carries one dropdown entry
    per used bind."""

    def test_preview_default_excludes_pii_columns(
        self, bofs_app_for_export_with_binds
    ):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Preview table reflects the default bind only.
        assert "experiment_score" in body
        assert "contact_email" not in body

    def test_preview_bind_shows_only_bind_data(
        self, bofs_app_for_export_with_binds
    ):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        _submit_pii_questionnaire(app, p, "alice@example.com")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export?bind=pii")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "contact_email" in body
        assert "alice@example.com" in body
        # Experiment data must not leak into the PII preview.
        assert "experiment_score" not in body
        # Download button on this page points at the per-bind endpoint.
        assert "/admin/export/download/pii" in body

    def test_preview_unknown_bind_falls_back_to_default(
        self, bofs_app_for_export_with_binds
    ):
        """A stale or mistyped ?bind=foo shouldn't 404 the preview page —
        the bind dropdown is the discovery surface for valid names. Fall
        back to the default-bind preview silently."""
        app = bofs_app_for_export_with_binds
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export?bind=does_not_exist")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Download button reverts to the default-bind URL, not /export/download/does_not_exist.
        assert "/admin/export/download/does_not_exist" not in body

    def test_navbar_export_dropdown_lists_used_binds(
        self, bofs_app_for_export_with_binds
    ):
        app = bofs_app_for_export_with_binds
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export")
        body = resp.data.decode("utf-8")
        # The Export navbar dropdown should have a "Main Database" entry
        # and a "pii" entry — but not entries for binds nobody uses.
        assert "Main Database" in body
        assert ">pii<" in body or 'pii</a>' in body

    def test_navbar_export_is_single_button_when_no_binds(
        self, bofs_app_for_export_no_binds
    ):
        app = bofs_app_for_export_no_binds
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/export")
        body = resp.data.decode("utf-8")
        # With no binds and no interaction logging, the navbar shows a
        # single "Export" link rather than a dropdown.
        assert "Main Database" not in body


class TestAsymmetricSubmission:
    """Participants who submit only one of the two bind's questionnaires.
    The per-bind CSV must include them only when a row actually exists on
    that bind, regardless of the row's field values (the original
    implementation used a value-shape heuristic that could drop blank-text
    PII submissions; this guards against that regression)."""

    def test_default_only_participant_absent_from_pii_csv(
        self, bofs_app_for_export_with_binds
    ):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        # No PII submission.

        results = Results()
        pii_csv = results.build_export_csv_for_bind("pii")

        # Header only, no data rows
        lines = [line for line in pii_csv.splitlines() if line]
        assert len(lines) == 1, (
            f"Expected only header in PII CSV, got: {pii_csv!r}"
        )

    def test_pii_only_participant_present_in_pii_csv(
        self, bofs_app_for_export_with_binds
    ):
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        # No default-bind submission.
        _submit_pii_questionnaire(app, p, "alice@example.com")

        results = Results()
        pii_csv = results.build_export_csv_for_bind("pii")

        header, data = pii_csv.splitlines()[0], pii_csv.splitlines()[1]
        cols = header.split(",")
        values = data.split(",")
        assert values[cols.index("participantID")] == str(p.participantID)
        assert values[cols.index("contact_email")] == "alice@example.com"

    def test_blank_pii_submission_still_appears_in_csv(
        self, bofs_app_for_export_with_binds
    ):
        """Regression guard for the original value-shape heuristic, which
        dropped participants whose cross-bind row had all blank/None
        string fields. The presence of the row in the bind's DB is what
        determines inclusion now, not the row's values."""
        app = bofs_app_for_export_with_binds
        p = _make_finished_participant(app)
        _submit_default_questionnaire(app, p, "42")
        # PII row with an empty email — the row exists in pii.db even
        # though every researcher-visible field is blank.
        _submit_pii_questionnaire(app, p, "")

        results = Results()
        pii_csv = results.build_export_csv_for_bind("pii")

        lines = [line for line in pii_csv.splitlines() if line]
        # Header + one data row
        assert len(lines) == 2
        cols = lines[0].split(",")
        values = lines[1].split(",")
        assert values[cols.index("participantID")] == str(p.participantID)

    def test_mixed_pids_only_pii_submitters_in_pii_csv(
        self, bofs_app_for_export_with_binds
    ):
        """Two participants, only one of whom submits the PII questionnaire.
        The PII CSV must list only the PII submitter."""
        app = bofs_app_for_export_with_binds
        p1 = _make_finished_participant(app)
        p2 = _make_finished_participant(app)
        _submit_default_questionnaire(app, p1, "42")
        _submit_default_questionnaire(app, p2, "99")
        _submit_pii_questionnaire(app, p2, "bob@example.com")

        results = Results()
        default_csv = results.build_export_csv_for_bind(None)
        pii_csv = results.build_export_csv_for_bind("pii")

        # Default CSV: both participants (header + 2 rows)
        default_lines = [line for line in default_csv.splitlines() if line]
        assert len(default_lines) == 3

        # PII CSV: only p2 (header + 1 row)
        pii_lines = [line for line in pii_csv.splitlines() if line]
        assert len(pii_lines) == 2
        cols = pii_lines[0].split(",")
        values = pii_lines[1].split(",")
        assert values[cols.index("participantID")] == str(p2.participantID)
