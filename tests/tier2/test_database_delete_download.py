"""Tier 2 tests for ``/admin/database_download`` and
``/admin/database_delete`` after per-bind support.

The hazard these guard against: a researcher who clicks Delete or
Download in the admin UI must not silently end up with partial state
(``main.db`` deleted but ``pii.db`` left intact, or a backup that
covers only one of the two files).
"""

import io
import os
import zipfile

import pytest


def _login(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["loggedIn"] = True
    return client


def _seed_one_participant_with_pii(app):
    p = app.db.Participant()
    p.finished = True
    p.externalID = "WORKER_A"
    app.db.session.add(p)
    app.db.session.commit()

    EClass = app.questionnaires["experiment"].db_class
    e = EClass()
    e.participantID = p.participantID
    e.tag = ""
    e.score = "42"
    app.db.session.add(e)

    CClass = app.questionnaires["contact"].db_class
    c = CClass()
    c.participantID = p.participantID
    c.tag = ""
    c.email = "alice@example.com"
    app.db.session.add(c)
    app.db.session.commit()
    return p


class TestDownloadAllAsZip:
    def test_download_returns_zip(self, bofs_app_with_file_binds):
        _seed_one_participant_with_pii(bofs_app_with_file_binds)
        client = _login(bofs_app_with_file_binds)

        resp = client.get("/admin/database_download")
        assert resp.status_code == 200
        assert resp.mimetype == "application/zip"
        assert "databases_" in resp.headers["Content-Disposition"]

    def test_zip_contains_both_db_files(self, bofs_app_with_file_binds):
        _seed_one_participant_with_pii(bofs_app_with_file_binds)
        client = _login(bofs_app_with_file_binds)

        resp = client.get("/admin/database_download")
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        names = set(zf.namelist())
        assert "main.db" in names
        assert "pii.db" in names

    def test_zip_entries_carry_real_data(self, bofs_app_with_file_binds):
        """The DB files in the zip are the actual files on disk —
        they should contain rows for the seeded participant."""
        _seed_one_participant_with_pii(bofs_app_with_file_binds)
        client = _login(bofs_app_with_file_binds)

        resp = client.get("/admin/database_download")
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        pii_bytes = zf.read("pii.db")
        # The pii DB has the email somewhere in its bytes — a coarse but
        # reliable signal that the file isn't empty.
        assert b"alice@example.com" in pii_bytes


class TestDeleteAllWithBackup:
    def test_delete_clears_default_and_bind_rows(self, bofs_app_with_file_binds):
        app = bofs_app_with_file_binds
        p = _seed_one_participant_with_pii(app)
        client = _login(app)

        resp = client.post("/admin/database_delete", data={
            "password": "test",
            "csrf_token": "fake",  # CSRF is disabled / generated via session
        }, follow_redirects=False)
        # Successful delete redirects to /admin/progress
        assert resp.status_code in (302, 303)

        # Both binds emptied
        assert app.db.session.query(app.db.Participant).count() == 0
        EClass = app.questionnaires["experiment"].db_class
        CClass = app.questionnaires["contact"].db_class
        assert app.db.session.query(EClass).count() == 0
        assert app.db.session.query(CClass).count() == 0

    def test_delete_writes_backup_zip(self, bofs_app_with_file_binds):
        app = bofs_app_with_file_binds
        _seed_one_participant_with_pii(app)
        project_root = os.path.abspath(app.root_path)
        before = set(os.listdir(project_root))
        client = _login(app)

        client.post("/admin/database_delete", data={"password": "test"})

        after = set(os.listdir(project_root))
        new_files = after - before
        backups = [name for name in new_files if name.startswith("backup_") and name.endswith(".zip")]
        assert len(backups) == 1, f"expected one backup zip, got {new_files}"

        backup_path = os.path.join(project_root, backups[0])
        with zipfile.ZipFile(backup_path) as zf:
            names = set(zf.namelist())
            assert "main.db" in names
            assert "pii.db" in names
            # Backup was taken BEFORE the rows were cleared, so the PII
            # data must still be in the zipped pii.db.
            assert b"alice@example.com" in zf.read("pii.db")

    def test_wrong_password_does_not_delete_or_backup(self, bofs_app_with_file_binds):
        app = bofs_app_with_file_binds
        _seed_one_participant_with_pii(app)
        project_root = os.path.abspath(app.root_path)
        before_files = set(os.listdir(project_root))
        client = _login(app)

        resp = client.post("/admin/database_delete", data={"password": "WRONG"})
        # Re-renders the form with the error message rather than redirecting
        assert resp.status_code == 200
        assert b"incorrect" in resp.data.lower()

        # Rows still present
        assert app.db.session.query(app.db.Participant).count() == 1
        # No backup written on a failed attempt
        after_files = set(os.listdir(project_root))
        assert not any(n.startswith("backup_") and n.endswith(".zip")
                       for n in (after_files - before_files))
