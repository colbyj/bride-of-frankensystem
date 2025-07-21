Admin Panel
===========

The BOFS admin panel provides a comprehensive interface for monitoring experiment progress, managing data, and analyzing results. This documentation covers all features and functionality of the admin interface.

Getting Started
---------------

Accessing the Admin Panel
~~~~~~~~~~~~~~~~~~~~~~~~~~

The admin panel is accessible at ``/admin`` when your BOFS application is running. For example, if your experiment is running at ``http://localhost:5000``, you can access the admin panel at ``http://localhost:5000/admin``.

Authentication
~~~~~~~~~~~~~~

Admin access is protected by password authentication configured in your TOML file:

.. code-block:: toml

    ADMIN_PASSWORD = 'your_secure_password_here'

After navigating to ``/admin``, you'll be redirected to a login page where you must enter this password. Once authenticated, you'll have access to all admin features until your session expires.

.. note::
    Use a strong, unique password for the ``ADMIN_PASSWORD`` setting. This password controls access to all participant data and experiment controls.

Admin Panel Features
--------------------

Progress Monitoring
~~~~~~~~~~~~~~~~~~~

The progress dashboard (``/admin/progress``) provides real-time monitoring of participant progress through your experiment.

.. image:: /examples/quickstart/minimal/minimal_admin.png
  :width: 800
  :alt: The admin page.


Real-time Dashboard
^^^^^^^^^^^^^^^^^^^

The dashboard automatically updates every 5 seconds and displays:

- **Current Participants**: Shows each active participant's progress through the experiment pages
- **Page Completion Status**: Visual indicators showing which pages each participant has completed
- **Live Updates**: Uses HTMX for seamless real-time updates without page refreshes

Participant exclusions can be toggled directly from this interface using checkboxes.

Summary Statistics
^^^^^^^^^^^^^^^^^^

The progress page includes summary statistics showing:

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

Data Export
~~~~~~~~~~~

Export Questionnaire Data
^^^^^^^^^^^^^^^^^^^^^^^^^^

The main export feature (``/admin/export``) allows you to download all questionnaire responses as CSV files.

Export Options:

- **Include Unfinished**: Option to include participants who haven't completed the experiment
- **Include Excluded**: Option to include participants marked as excluded
- **Preview Mode**: View data in HTML table format before downloading
- **Automatic Timestamps**: CSV files include timestamp in filename

Grid Timing Data Export
^^^^^^^^^^^^^^^^^^^^^^^

When ``LOG_GRID_CLICKS`` is enabled in your configuration, detailed timing data for radiogrid questions becomes available at ``/admin/export_item_timing``. This exports:

- Individual item response times within grid questions
- Click-by-click timing logs
- Detailed interaction patterns

Custom Table Exports
^^^^^^^^^^^^^^^^^^^^^

Any database table can be exported as CSV via ``/admin/table_csv/<table_name>``. This includes:

- Built-in BOFS tables (Participant, Progress, Response)
- Custom tables defined in your blueprints
- Proper CSV escaping and formatting

Results Analysis
~~~~~~~~~~~~~~~~

Summary Statistics
^^^^^^^^^^^^^^^^^^

The results page (``/admin/results``) automatically calculates descriptive statistics for all numeric fields in your data:

- **N** (sample size)
- **Min/Max** values
- **Mean** and **Median**
- **Standard Deviation** and **Standard Error**
- **Variance**

Results are grouped by experimental condition and cached for 2 minutes to improve performance.

Interactive Visualizations
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Box plots are automatically generated for numeric fields at ``/admin/results_boxplot/<field_name>``. These interactive Plotly.js visualizations include:

- Distribution by experimental condition
- Outlier detection and highlighting
- Interactive zoom and pan capabilities
- Hover tooltips with detailed values

Questionnaire Management
~~~~~~~~~~~~~~~~~~~~~~~~

Questionnaire Preview
^^^^^^^^^^^^^^^^^^^^^

Individual questionnaires can be previewed at ``/admin/preview_questionnaire/<questionnaire_name>``. This feature:

- Renders questionnaires exactly as participants see them
- Displays JSON parsing errors for malformed questionnaire files
- Allows condition switching for conditional questions
- Marks questionnaires that have live participant data with an asterisk (*)

Simple HTML Preview
^^^^^^^^^^^^^^^^^^^

Plain HTML rendering is available at ``/admin/questionnaire_html/<name>`` for:

- Embedding questionnaires in other contexts
- Printing questionnaire content
- Viewing without admin template styling

Procedure Visualization
^^^^^^^^^^^^^^^^^^^^^^^

The procedure page (``/admin/preview_procedure``) generates a visual flowchart of your experiment using Mermaid diagrams. This automatically creates:

- Page flow diagrams based on your ``PAGE_LIST`` configuration
- Branching logic visualization
- Condition-specific routing paths

Database Management
~~~~~~~~~~~~~~~~~~~

Table Viewer
^^^^^^^^^^^^

The table viewer (``/admin/table_view/<table_name>``) provides:

- Live view of any database table contents
- AJAX-based table refresh for real-time updates
- Automatic column type detection and appropriate display formatting

SQLite-specific Features
^^^^^^^^^^^^^^^^^^^^^^^^

For SQLite databases, additional management options are available:

Database Download (``/admin/database_download``):

- Direct download of the complete SQLite database file
- Useful for backup and offline analysis

Database Delete (``/admin/database_delete``):

- Password-protected database clearing functionality
- Automatic backup creation before deletion
- Preserves table structure while clearing data

.. warning::
    Database deletion is irreversible. Always ensure you have backups before using this feature.

Configuration Options
---------------------

Admin-related Configuration Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. table:: Admin Configuration
    :widths: 30,15,55

    ============================ ======= ==================
    Variable                     Type    Description
    ============================ ======= ==================
    ADMIN_PASSWORD               string  **Required**. Password for admin panel access.
    USE_ADMIN                    boolean Enable/disable admin panel entirely (default: True).
    LOG_GRID_CLICKS              boolean Enable detailed radiogrid timing logs for export (default: False).
    ADDITIONAL_ADMIN_PAGES       list    Custom admin pages from blueprints.
    ============================ ======= ==================

Custom Admin Pages
~~~~~~~~~~~~~~~~~~

Blueprints can extend the admin panel by defining custom pages in the ``ADDITIONAL_ADMIN_PAGES`` configuration:

.. code-block:: toml

    ADDITIONAL_ADMIN_PAGES = [
        {name = "Custom Analysis", route = "my_blueprint.custom_analysis"},
        {name = "External Tool", url = "https://example.com/tool"}
    ]

Custom pages appear in the admin navigation dropdown and can be either:

- **Routes**: References to Flask routes in your blueprints
- **URLs**: Direct links to external tools or pages

Security Considerations
-----------------------

Admin Panel Security
~~~~~~~~~~~~~~~~~~~~~

- **Strong Passwords**: Use complex, unique passwords for ``ADMIN_PASSWORD``
- **Access Control**: The admin panel provides access to all participant data
- **Session Management**: Admin sessions expire and require re-authentication
- **Network Security**: Consider using HTTPS for production deployments

Data Protection
~~~~~~~~~~~~~~~

- **Backup Strategy**: Regularly backup your database, especially before using delete functions
- **Export Security**: Be mindful of participant privacy when exporting data
- **Access Logging**: Consider implementing access logging for audit trails

Integration with Custom Blueprints
-----------------------------------

Custom Admin Routes
~~~~~~~~~~~~~~~~~~~

Blueprints can create admin-protected routes using the ``@verify_admin`` decorator:

.. code-block:: python

    from BOFS.admin.util import verify_admin
    from flask import Blueprint

    my_blueprint = Blueprint('my_blueprint', __name__)

    @my_blueprint.route('/admin/my_custom_page')
    @verify_admin
    def my_custom_admin_page():
        return render_template('my_admin_page.html')

This ensures your custom admin pages are protected by the same authentication system as the built-in admin features.

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

**Login Problems**:

- Verify ``ADMIN_PASSWORD`` is set correctly in your configuration
- Check for browser session issues (try incognito/private browsing)
- Ensure cookies are enabled in your browser

**Export Issues**:

- Verify sufficient disk space for large exports
- Check file permissions in the application directory
- For timing exports, ensure ``LOG_GRID_CLICKS`` is enabled

**Performance Issues**:

- Results are cached for 2 minutes; wait for cache refresh for updated statistics
- For large datasets, consider using database-specific optimization such as indexes
- AJAX updates may slow with very large participant counts

**Database Issues**:

- SQLite features only work with SQLite databases
- Ensure database file permissions allow read/write access
- For database corruption, restore from backup
