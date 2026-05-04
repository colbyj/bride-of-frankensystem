Configuration Reference
=======================

Every option BOFS reads from a project's ``.toml`` file. For a guided introduction, see :doc:`/building/page_flow`.

Required Settings
-----------------

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Variable
     - Type
     - Description
   * - ``SQLALCHEMY_DATABASE_URI``
     - string
     - Database connection string. Use ``sqlite:///filename.db`` for SQLite or ``postgresql://user:pass@host/db`` for PostgreSQL.
   * - ``TITLE``
     - string
     - Study title shown in browser tab and page headers.
   * - ``PORT``
     - integer
     - Port number for the web server (e.g., ``5000``).
   * - ``ADMIN_PASSWORD``
     - string
     - Password for accessing the admin panel at ``/admin``.
   * - ``PAGE_LIST``
     - list
     - Defines the sequence of pages participants see. See `PAGE_LIST Configuration`_ below.

Application Settings
--------------------

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``APPLICATION_ROOT``
     - string
     - ``""``
     - URL prefix if hosting at a subpath (e.g., ``/study1``). Leave unset when hosting at the root.
   * - ``USE_BREADCRUMBS``
     - boolean
     - ``true``
     - Show a breadcrumbs-style progress indicator to participants.
   * - ``USE_LOGO``
     - boolean
     - ``true``
     - Display the BOFS logo in the page header.
   * - ``HEADER_COLOR``
     - string
     - *(unset)*
     - Background color of the title bar. Accepts a CSS hex color (e.g., ``"#8CB737"``), a named color (e.g., ``"navy"``), or ``rgb()``/``rgba()``/``hsl()``/``hsla()`` notation. When unset, the default green from the stylesheet is used.
   * - ``WAITRESS_THREADS``
     - integer
     - ``16``
     - Number of Waitress worker threads used in production (non-debug) mode. See :doc:`/deploying/server`.
   * - ``SECRET_KEY``
     - string
     - *(auto-generated)*
     - Flask session signing key. BOFS generates a random key on first run and stores it in the ``app_meta`` database table; the generated key persists across restarts. A value in the config is migrated into the database on first run and then ignored. Documented here for completeness — do not set this manually.

Admin Panel Settings
--------------------

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``USE_ADMIN``
     - boolean
     - ``true``
     - Enable or disable the admin panel entirely.
   * - ``ADDITIONAL_ADMIN_PAGES``
     - list
     - ``[]``
     - Custom admin pages contributed by blueprints. See :doc:`/building/monitoring_data`.
   * - ``LOG_QUESTIONNAIRE_INTERACTIONS``
     - boolean
     - ``false``
     - Log focus, blur, change, paste, and visibility events for every input on every questionnaire. Text inputs additionally record per-field authenticity signals (keystrokes, backspaces, pastes, pasted character count, final length, total focus duration, time-to-first-keystroke). See :doc:`/building/monitoring_data`.
   * - ``LOG_GRID_CLICKS``
     - boolean
     - *(deprecated)*
     - Deprecated alias for ``LOG_QUESTIONNAIRE_INTERACTIONS``. If both keys are absent, ``LOG_QUESTIONNAIRE_INTERACTIONS`` is used. If only ``LOG_GRID_CLICKS`` is present, its value is copied to ``LOG_QUESTIONNAIRE_INTERACTIONS`` and a warning is printed. Rename to ``LOG_QUESTIONNAIRE_INTERACTIONS`` to silence the warning.
   * - ``EXPORT``
     - list
     - ``[]``
     - Custom export definitions for blueprint-defined tables. Each entry is a dict describing a table, fields, and optional grouping. Populated automatically from loaded blueprints; can also be set in the project config.

Session and Participant Settings
--------------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``RETRIEVE_SESSIONS``
     - boolean
     - ``true``
     - If the external ID was used before, attempt to restore the participant's session and redirect to where they left off.
   * - ``ALLOW_RETAKES``
     - boolean
     - ``false``
     - When ``false``, prevents the same external ID from being used twice.
   * - ``ABANDONED_MINUTES``
     - integer
     - ``5``
     - Minutes of inactivity before a participant is considered abandoned.
   * - ``COUNTS_INCLUDE_ABANDONED``
     - boolean
     - ``false``
     - Include abandoned participants when balancing condition assignment. Abandoned participants are not counted when balancing conditions by default.

Security Settings
-----------------

These settings control IP-based brute-force protection on the admin login,
binding sessions to the IP they were created on, and how BOFS resolves the
real client IP behind a reverse proxy. See :doc:`/deploying/server` for
deployment context.

.. list-table::
   :header-rows: 1
   :widths: 30 15 20 35

   * - Variable
     - Type
     - Default
     - Description
   * - ``BRUTE_FORCE_PROTECTION``
     - boolean
     - ``true``
     - Master kill-switch. When ``false``, IP banning, login-attempt tracking,
       and session IP binding are all bypassed. Useful for emergency recovery
       if an admin locks themselves out.
   * - ``BRUTE_FORCE_AUTO_TRUST_ADMIN``
     - boolean
     - ``true``
     - When ``true``, a successful admin login adds the IP to a persistent
       allowlist (the ``admin_trusted_ip`` table) and exempts it from future
       bans. Acts as the primary self-service safeguard against admin self-lockout.
   * - ``BRUTE_FORCE_MAX_ATTEMPTS``
     - integer
     - ``5``
     - Failed admin logins per IP per window before a ban is issued.
   * - ``BRUTE_FORCE_WINDOW_MINUTES``
     - integer
     - ``15``
     - Sliding window for counting admin login failures.
   * - ``BRUTE_FORCE_BAN_SCHEDULE``
     - list of integers
     - ``[1, 2, 5, 15, 60, 360, 1440, 10080]``
     - Progressive ban duration in minutes. The IP's prior ban count indexes
       into the list (1m, 2m, 5m, 15m, 1h, 6h, 1d, 7d). The final entry
       sticks for any further bans. Historical ban rows are kept so the
       count is accurate across time.
   * - ``BRUTE_FORCE_PROBE_URLS``
     - list of strings
     - *(curated list, see below)*
     - Paths that instantly ban any visiting IP — used to catch scanners
       hitting well-known attack targets like ``/.env`` or ``/wp-admin``.
       Match is exact-or-prefix. If a custom blueprint legitimately serves
       any of these paths, remove that entry.
   * - ``BRUTE_FORCE_HOSTILE_UA_PATTERNS``
     - list of strings
     - ``["sqlmap", "nikto", "nmap", "dirbuster", "gobuster", "masscan", "WPScan", "acunetix", "nessus"]``
     - Case-insensitive substring matches against the request's
       ``User-Agent``. A match instant-bans the IP. This is defense-in-depth
       rather than a primary control, since scanners can mask their user-agent.
   * - ``SESSION_BIND_TO_IP_PARTICIPANT``
     - boolean
     - ``true``
     - When ``true``, a participant session is invalidated if the IP it was
       created from differs from the current request's IP. Set to ``false``
       for studies with mobile users who legitimately switch networks
       (cellular to wifi) mid-session, since each network change produces a
       new public IP. Admin sessions are always bound — there is no opt-out.
   * - ``TRUSTED_IPS``
     - list of strings
     - ``[]``
     - Static allowlist that bypasses all IP-based protection. Combines with
       the runtime ``admin_trusted_ip`` table.
   * - ``BEHIND_REVERSE_PROXY``
     - boolean
     - ``false``
     - Set to ``true`` if BOFS runs behind Caddy or nginx so the real
       client IP is read from ``X-Forwarded-For`` (via Werkzeug's
       ``ProxyFix``). When ``false``, ``X-Real-IP`` and ``X-Forwarded-For``
       are ignored — they are spoofable when nothing trusted is in front of
       the app.

The default ``BRUTE_FORCE_PROBE_URLS`` list:

.. code-block:: toml

    BRUTE_FORCE_PROBE_URLS = [
        "/.env",
        "/.git",
        "/.aws",
        "/wp-admin",
        "/wp-login.php",
        "/wp-includes",
        "/wp-content",
        "/xmlrpc.php",
        "/phpmyadmin",
        "/phpMyAdmin",
        "/administrator",
        "/admin.php",
        "/server-status",
        "/actuator",
        "/vendor/phpunit",
        "/cgi-bin",
        "/.DS_Store",
        "/.htaccess",
        "/.svn",
    ]

Recovery from a self-imposed lockout (the auto-trust list takes care of
the common case once an admin has logged in successfully even once from
the IP they're using):

1. Add the IP to ``TRUSTED_IPS`` in ``config.toml`` and restart.
2. Set ``BRUTE_FORCE_PROTECTION = false`` in ``config.toml`` and restart.
3. Edit the database directly: ``DELETE FROM banned_ip WHERE ipAddress = '...';``
   and optionally ``DELETE FROM admin_trusted_ip WHERE ipAddress = '...';``.

External ID Settings (MTurk/Prolific)
-------------------------------------

These settings control the ``/external_id`` page for collecting participant IDs from recruitment platforms. See :doc:`/deploying/recruiting`.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``EXTERNAL_ID_LABEL``
     - string
     - ``"Mechanical Turk Worker ID"``
     - Label for the external ID field.
   * - ``EXTERNAL_ID_PROMPT``
     - string
     - ``"Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."``
     - Instructions shown above the ID input field.

Completion Settings
-------------------

These settings control the ``/end`` page behavior. See :doc:`/deploying/recruiting`.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``GENERATE_COMPLETION_CODE``
     - boolean
     - ``true``
     - Generate a random completion code for each participant.
   * - ``STATIC_COMPLETION_CODE``
     - string
     - *(unset)*
     - Use the same completion code for all participants.
   * - ``COMPLETION_CODE_MESSAGE``
     - string
     - ``"Please copy and paste this code into the MTurk form:"``
     - Message displayed alongside the completion code.
   * - ``OUTGOING_URL``
     - string
     - *(unset)*
     - Redirect participants to this URL at study end instead of showing a completion code. Useful for Prolific redirects.

Experimental Conditions
-----------------------

Define experimental conditions for random assignment. See :doc:`/building/conditions_branching`.

.. code-block:: toml

    CONDITIONS = [
        {label="Control", enabled=true},
        {label="Treatment A", enabled=true},
        {label="Treatment B", enabled=false}
    ]

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Property
     - Description
   * - ``label``
     - Human-readable name for the condition (shown in admin panel).
   * - ``enabled``
     - Whether to assign new participants to this condition. Set to ``false`` to stop assignment without removing the condition.

Participants are assigned to the condition with the fewest participants. Condition numbers start at 1. Participants without an assigned condition have condition 0.

Longitudinal Condition Lookup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For longitudinal studies where condition assignment must match a prior session, BOFS can look up conditions from an external source. See :doc:`/building/longitudinal`.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``CONDITIONS_FROM_CSV``
     - string
     - *(unset)*
     - Path to a CSV file (relative to the project working directory) mapping participant IDs to condition numbers. The file must have at least two columns: the participant ID and the condition. Mutually exclusive with ``CONDITIONS_FROM_DB``.
   * - ``CONDITIONS_FROM_DB``
     - string
     - *(unset)*
     - SQLAlchemy connection URI for an external database from which condition assignments are looked up by participant ID. Mutually exclusive with ``CONDITIONS_FROM_CSV``.

PAGE_LIST Configuration
-----------------------

The ``PAGE_LIST`` defines the sequence of pages participants encounter. See :doc:`/building/page_flow`.

**Basic Structure**

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Survey", path="questionnaire/demographics"},
        {name="End", path="end"}
    ]

**Page Entry Properties**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Property
     - Description
   * - ``name``
     - Human-readable name shown in admin panel and progress tracking.
   * - ``path``
     - URL route that determines what content to display.

**Required Pages**

- **First page** must be one of: ``consent``, ``consent_nc``, ``create_participant``, or ``create_participant_nc``
- **Last page** must be ``end``

**Available Page Types**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Path Format
     - Description
   * - ``consent``
     - Built-in consent form with condition assignment. See :doc:`/building/consent`.
   * - ``consent_nc``
     - Consent form without condition assignment. See :doc:`/building/consent`.
   * - ``create_participant``
     - Create participant with condition assignment (no consent form).
   * - ``create_participant_nc``
     - Create participant without condition assignment.
   * - ``external_id``
     - Collect external ID (MTurk Worker ID, Prolific ID, etc.).
   * - ``questionnaire/name``
     - Display questionnaire from ``questionnaires/name.json``.
   * - ``instructions/name``
     - Show page from ``templates/instructions/name.html`` with a Continue button.
   * - ``simple/name``
     - Show page from ``templates/simple/name.html`` with manual navigation.
   * - ``end``
     - Built-in completion page with code or redirect.

**Conditional Routing**

Show different pages based on participant condition. See :doc:`/building/conditions_branching`.

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {conditional_routing=[
            {condition=1, page_list=[
                {name="Control Task", path="instructions/control"}
            ]},
            {condition=2, page_list=[
                {name="Treatment Task", path="instructions/treatment"}
            ]}
        ]},
        {name="End", path="end"}
    ]

Database Configuration
----------------------

**SQLite**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"

**PostgreSQL**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "postgresql://username:password@localhost:5432/database"

**MySQL**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "mysql+pymysql://username:password@localhost/database"

Example Configurations
----------------------

**Minimal Configuration**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"
    ADMIN_PASSWORD = "admin"

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Survey", path="questionnaire/survey"},
        {name="End", path="end"}
    ]

**MTurk/Prolific Study**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"
    TITLE = "Research Study"
    ADMIN_PASSWORD = "secure_password"

    EXTERNAL_ID_LABEL = "MTurk Worker ID"
    EXTERNAL_ID_PROMPT = "Please enter your MTurk Worker ID."
    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false
    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy this code into MTurk:"

    PAGE_LIST = [
        {name="External ID", path="external_id"},
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Task", path="questionnaire/task"},
        {name="End", path="end"}
    ]

**A/B Testing Study**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"
    TITLE = "Decision Making Study"
    ADMIN_PASSWORD = "secure_password"

    CONDITIONS = [
        {label="Control", enabled=true},
        {label="Treatment", enabled=true}
    ]

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {conditional_routing=[
            {condition=1, page_list=[
                {name="Control Instructions", path="instructions/control"}
            ]},
            {condition=2, page_list=[
                {name="Treatment Instructions", path="instructions/treatment"}
            ]}
        ]},
        {name="Main Task", path="questionnaire/task"},
        {name="End", path="end"}
    ]
