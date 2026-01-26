Configuration Reference
=======================

This page is a comprehensive reference for all configuration options in BOFS project ``.toml`` files. For a tutorial-style introduction, see :doc:`/getting_started/project_configuration`.

Required Settings
-----------------

These settings must be present in every BOFS configuration file.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Variable
     - Type
     - Description
   * - ``SQLALCHEMY_DATABASE_URI``
     - string
     - Database connection string. Use ``sqlite:///filename.db`` for development or ``postgresql://user:pass@host/db`` for production.
   * - ``SECRET_KEY``
     - string
     - A unique random string for session security. Generate with ``python -c "import secrets; print(secrets.token_hex(32))"``.
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
     - URL prefix if hosting at a subpath (e.g., ``/study1``). Rarely needed.
   * - ``USE_BREADCRUMBS``
     - boolean
     - ``false``
     - Show breadcrumbs-style progress bar to participants.

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
     - Custom admin pages from blueprints. See :doc:`/getting_started/admin`.
   * - ``LOG_GRID_CLICKS``
     - boolean
     - ``false``
     - Log timestamps for each radio button click in grids. Enables detailed timing export.

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
     - ``false``
     - If the external ID was used before, attempt to restore the participant's session and redirect to where they left off.
   * - ``ALLOW_RETAKES``
     - boolean
     - ``true``
     - When ``false``, prevents the same external ID from being used twice.
   * - ``ABANDONED_MINUTES``
     - integer
     - ``30``
     - Minutes of inactivity before a participant is considered abandoned.
   * - ``COUNTS_INCLUDE_ABANDONED``
     - boolean
     - ``false``
     - Include abandoned participants when balancing condition assignment.

External ID Settings (MTurk/Prolific)
-------------------------------------

These settings control the ``/external_id`` page for collecting participant IDs from recruitment platforms.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``EXTERNAL_ID_LABEL``
     - string
     - ``"ID"``
     - Label for the external ID field (e.g., ``"MTurk Worker ID"``).
   * - ``EXTERNAL_ID_PROMPT``
     - string
     - ``""``
     - Instructions shown above the ID input field.

Completion Settings
-------------------

These settings control the ``/end`` page behavior.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Variable
     - Type
     - Default
     - Description
   * - ``GENERATE_COMPLETION_CODE``
     - boolean
     - ``false``
     - Generate a random completion code for each participant.
   * - ``STATIC_COMPLETION_CODE``
     - string
     - ``""``
     - Use the same completion code for all participants.
   * - ``COMPLETION_CODE_MESSAGE``
     - string
     - ``"Your code is:"``
     - Message displayed with the completion code.
   * - ``OUTGOING_URL``
     - string
     - ``""``
     - Redirect participants to this URL instead of showing a completion code. Useful for Prolific redirects.

Experimental Conditions
-----------------------

Define experimental conditions for random assignment:

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
     - Whether to assign participants to this condition. Set to ``false`` to disable without removing.

Participants are assigned to the condition with the fewest participants. Condition numbers start at 1. Participants without an assigned condition have condition 0.

PAGE_LIST Configuration
-----------------------

The ``PAGE_LIST`` defines the sequence of pages participants encounter.

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
     - Built-in consent form with condition assignment.
   * - ``consent_nc``
     - Consent form without condition assignment.
   * - ``create_participant``
     - Create participant with condition assignment (no consent form).
   * - ``create_participant_nc``
     - Create participant without condition assignment.
   * - ``external_id``
     - Collect external ID (MTurk Worker ID, Prolific ID, etc.).
   * - ``questionnaire/name``
     - Display questionnaire from ``questionnaires/name.json``.
   * - ``instructions/name``
     - Show page from ``templates/instructions/name.html`` with Continue button.
   * - ``simple/name``
     - Show page from ``templates/simple/name.html`` with manual navigation.
   * - ``end``
     - Built-in completion page with code or redirect.

**Conditional Routing**

Show different pages based on participant condition:

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

**SQLite (Development)**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"

**PostgreSQL (Production)**

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
    SECRET_KEY = "your-unique-secret-key-here"
    ADMIN_PASSWORD = "admin"

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Survey", path="questionnaire/survey"},
        {name="End", path="end"}
    ]

**MTurk/Prolific Study**

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"
    SECRET_KEY = "your-unique-secret-key-here"
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
    SECRET_KEY = "your-unique-secret-key-here"
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
