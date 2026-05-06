Monitoring and Exporting Data
=============================

Every BOFS project ships with an admin panel for monitoring participants, exporting data, previewing questionnaires, and inspecting the underlying database.

Accessing the Panel
-------------------

The admin panel lives at ``/admin``. For a project running locally on port 5000, that's http://localhost:5000/admin.

Set the password in your ``.toml`` file:

.. code-block:: toml

    ADMIN_PASSWORD = 'your_secure_password_here'

This password protects all participant data and any destructive controls (such as clearing the database), so use a strong, unique value rather than a placeholder.

Progress Monitoring
-------------------

``/admin/progress`` shows each active participant's position in the experiment. The page updates every 5 seconds via HTMX and includes per-participant exclusion checkboxes.

.. image:: /examples/quickstart/page_admin.png
  :width: 800
  :alt: The admin progress page.

The same page reports summary statistics, broken down by experimental condition:

.. table:: Progress Statistics
    :widths: 25,75

    ======================== ==================
    Metric                   Description
    ======================== ==================
    Total Participants       Count by experimental condition
    Abandoned Participants   Those who haven't progressed within the configured time limit
    In-Progress Participants Currently active participants
    Finished Participants    Those who have completed all pages
    Average Duration         Mean completion time by condition
    Min/Max Duration         Fastest and slowest completion times
    ======================== ==================

Participant Detail View
~~~~~~~~~~~~~~~~~~~~~~~

Clicking a participant ID on the progress dashboard opens that participant's
detail view (``/admin/participant/<id>``). This page reconstructs the
participant's run through the experiment as a timeline, with one card per
page in their ``PAGE_LIST`` (condition-aware, so participants in different
conditions see only the pages that apply to them).

Each timeline card shows:

- **Status**: Completed, In Progress, or Not Reached.
- **Timing**: when the page was started, when it was submitted, and the
  duration on the page.
- **Submitted data**, broken down by page type:

  - *Questionnaire pages* — every field's prompt, field ID, and the
    participant's response, plus any calculated fields defined on the
    questionnaire.
  - *Custom pages* writing to a JSONTable — the calculated export fields
    from the table's ``exports`` block, scoped to this participant. To opt
    a custom page in, decorate its view function with ``@page_tables``;
    see :doc:`/reference/custom_tables` for details.

The page header also shows the participant's external ID (e.g. Prolific PID),
assigned condition, total duration, last-active timestamp, and an Excluded
badge when applicable.

Data Export
-----------

``/admin/export`` downloads questionnaire responses as CSV. Options include excluding unfinished or excluded participants, previewing the table in HTML before downloading, and automatic timestamping of the filename.

For questionnaire interaction data (only collected when ``LOG_QUESTIONNAIRE_INTERACTIONS`` is enabled), use ``/admin/export_item_timing``. This exports a flat event log — one row per event — with participantID, mTurkID, questionnaire, tag, questionID, eventType (focus, blur, change, paste, visibility), timestamp, and value.

Any database table — built-in (``Participant``, ``Progress``, ``Response``) or defined by a custom blueprint — can be exported individually via ``/admin/table_csv/<table_name>``.

Results Analysis
----------------

``/admin/results`` calculates descriptive statistics (N, min/max, mean, median, standard deviation, standard error, variance) for every numeric field, grouped by condition. The page is cached for two minutes.

For each numeric field, ``/admin/results_boxplot/<field_name>`` renders an interactive Plotly.js box plot showing the distribution by condition, with outliers, zoom, pan, and hover tooltips.

Questionnaire Management
------------------------

``/admin/preview_questionnaire/<name>``
  Renders a questionnaire as participants would see it. Surfaces JSON parsing errors, lets you switch conditions for previewing conditional questions, and marks questionnaires that already have live participant data with an asterisk.

``/admin/questionnaire_html/<name>``
  Plain HTML rendering with no admin chrome — useful for embedding, printing, or sharing.

``/admin/preview_procedure``
  Generates a Mermaid flowchart of your ``PAGE_LIST``, including the per-condition routes from any ``conditional_routing`` blocks.

Database Management
-------------------

``/admin/table_view/<table_name>`` shows the live contents of any database table with AJAX-driven refresh and automatic column-type detection.

For SQLite databases only:

* ``/admin/database_download`` downloads the full database file — useful for backups or offline analysis.
* ``/admin/database_delete`` clears the database. The action is password-protected; only the table structure survives. It attempts to copy the SQLite file to a timestamped sibling first, but treat that copy as a courtesy, not a backup — it is not verified, does not include WAL/SHM sidecar files, and may not be reachable from where you're running BOFS (e.g. inside a container).

.. warning::
    Database deletion is irreversible. Take your own backup (``/admin/database_download``, or copy the ``.db`` file directly) before using it.

Configuration
-------------

.. table:: Admin Configuration
    :widths: 30,15,55

    ================================ ======= ==================
    Variable                         Type    Description
    ================================ ======= ==================
    ADMIN_PASSWORD                   string  **Required.** Password for admin panel access.
    USE_ADMIN                        boolean Enable or disable the admin panel entirely (default: ``true``).
    LOG_QUESTIONNAIRE_INTERACTIONS   boolean Log questionnaire interaction events for export (default: ``false``).
    ADDITIONAL_ADMIN_PAGES           list    Custom admin pages from blueprints (see below).
    ================================ ======= ==================

Adding Custom Admin Pages
~~~~~~~~~~~~~~~~~~~~~~~~~

``ADDITIONAL_ADMIN_PAGES`` adds entries to the admin navigation. Each entry is either a Flask route from one of your blueprints or an external URL:

.. code-block:: toml

    ADDITIONAL_ADMIN_PAGES = [
        {name = "Custom Analysis", route = "my_blueprint.custom_analysis"},
        {name = "External Tool", url = "https://example.com/tool"}
    ]

To protect a custom Flask route with the same authentication as the built-in admin pages, decorate it with ``@verify_admin``:

.. code-block:: python

    from BOFS.admin.util import verify_admin
    from flask import Blueprint

    my_blueprint = Blueprint('my_blueprint', __name__)

    @my_blueprint.route('/admin/my_custom_page')
    @verify_admin
    def my_custom_admin_page():
        return render_template('my_admin_page.html')

Security
--------

The admin panel exposes every participant's data and includes destructive controls. For production deployments:

* Pick a strong, unique password for ``ADMIN_PASSWORD``.
* Serve the site over HTTPS.
* Back up the database before using ``/admin/database_delete``.
* Be deliberate when exporting data — the CSV files contain anything participants entered.

Troubleshooting
---------------

**Login problems**
  Confirm ``ADMIN_PASSWORD`` is set correctly. Try an incognito window to rule out a stale session, and check that cookies are enabled.

**Export problems**
  For large studies, check available disk space and that the application directory is writable. For interaction timing exports specifically, ``LOG_QUESTIONNAIRE_INTERACTIONS`` must be enabled.

**Slow results page**
  Results are cached for two minutes — wait for the cache to refresh before assuming new data isn't loading. For very large datasets, add database indexes on frequently queried columns.

**SQLite-only features unavailable**
  ``/admin/database_download`` and ``/admin/database_delete`` only work when the project uses SQLite. With PostgreSQL or another backend, use the database's own tools.
