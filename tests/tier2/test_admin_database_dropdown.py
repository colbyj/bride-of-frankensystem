"""Tier 2 tests for the admin Database dropdown categorisation.

The dropdown sorts tables into three buckets so the storage layout is
visible at a glance:

* **System Data** — framework default-bind tables (participant, progress,
  display, banned_ip, etc.). Fixed list defined in
  ``BOFS.admin.views._SYSTEM_TABLE_NAMES``.
* **Per-bind submenus** — one header per configured non-default bind,
  listing every table on that engine.
* **Tables** — researcher-defined default-bind tables (questionnaire_\\*,
  table_\\*, blueprint models).
"""

import pytest


def _get_template_vars(app):
    """Push enough request context to call the admin context processor."""
    with app.test_request_context("/admin/"):
        from BOFS.admin import views as admin_views
        return admin_views.inject_template_vars()


class TestCategorisationNoBinds:
    def test_system_tables_present(self, bofs_app):
        vars_ = _get_template_vars(bofs_app)
        assert "participant" in vars_["systemTables"]
        assert "progress" in vars_["systemTables"]
        assert "display" in vars_["systemTables"]
        assert "banned_ip" in vars_["systemTables"]
        assert "admin_trusted_ip" in vars_["systemTables"]
        assert "login_attempt" in vars_["systemTables"]

    def test_app_meta_excluded_from_everything(self, bofs_app):
        vars_ = _get_template_vars(bofs_app)
        # app_meta carries the SECRET_KEY — exposing it through the
        # generic table viewer would undo the reason it was moved out of
        # config.toml in the first place.
        all_visible = (
            vars_["systemTables"]
            + vars_["userTables"]
            + [n for ns in vars_["bindTables"].values() for n in ns]
        )
        assert "app_meta" not in all_visible

    def test_session_store_visible_under_system_data(self, bofs_app):
        vars_ = _get_template_vars(bofs_app)
        assert "session_store" in vars_["systemTables"]

    def test_no_bind_submenus_when_no_binds_configured(self, bofs_app):
        vars_ = _get_template_vars(bofs_app)
        assert vars_["bindTables"] == {}
        assert vars_["exportBinds"] == []


class TestCategorisationWithBinds:
    def test_pii_questionnaire_lands_in_pii_submenu(
        self, bofs_app_for_export_with_binds
    ):
        vars_ = _get_template_vars(bofs_app_for_export_with_binds)
        assert "pii" in vars_["bindTables"]
        assert "questionnaire_contact" in vars_["bindTables"]["pii"]
        # And does NOT appear in the default-bind categories
        assert "questionnaire_contact" not in vars_["systemTables"]
        assert "questionnaire_contact" not in vars_["userTables"]

    def test_default_questionnaire_in_user_tables(
        self, bofs_app_for_export_with_binds
    ):
        vars_ = _get_template_vars(bofs_app_for_export_with_binds)
        assert "questionnaire_experiment" in vars_["userTables"]

    def test_export_binds_lists_used_binds_only(
        self, bofs_app_for_export_with_binds
    ):
        vars_ = _get_template_vars(bofs_app_for_export_with_binds)
        assert vars_["exportBinds"] == ["pii"]


class TestTableViewRoutesAcrossBinds:
    def test_cross_bind_table_view_loads(self, bofs_app_for_export_with_binds):
        """The /admin/table_view/<name> route must find tables that live
        on a non-default engine — those don't appear in db.metadata."""
        app = bofs_app_for_export_with_binds
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True

        resp = client.get("/admin/table_view/questionnaire_contact")
        assert resp.status_code == 200

    def test_blocked_table_view_still_404s(self, bofs_app):
        client = bofs_app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True
        resp = client.get("/admin/table_view/app_meta")
        assert resp.status_code == 404

    def test_unknown_table_404s(self, bofs_app):
        client = bofs_app.test_client()
        with client.session_transaction() as sess:
            sess["loggedIn"] = True
        resp = client.get("/admin/table_view/no_such_table")
        assert resp.status_code == 404
