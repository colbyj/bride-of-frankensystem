Setting Up Your Page Flow
=========================

A BOFS project is configured by one TOML file — typically ``config.toml`` — that defines settings, the page sequence (``PAGE_LIST``), and condition assignment. This page covers the configuration concepts you'll use most often. The full setting-by-setting reference lives at :doc:`/reference/configuration`.

TOML basics
-----------

TOML is a plain text format with key-value pairs, ``#`` for comments, and square brackets for lists:

.. code-block:: toml

   TITLE = "My Research Study"
   PORT = 5000

   # Comments start with #.

   PAGE_LIST = [
       {name="Consent", path="consent"},
       {name="End", path="end"}
   ]

Required settings
-----------------

Every BOFS project needs at least these:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Setting
     - What it does
   * - ``TITLE``
     - Study name shown in the browser tab and admin panel.
   * - ``PORT``
     - The port the project runs on (e.g., ``5000`` for ``http://localhost:5000``).
   * - ``SQLALCHEMY_DATABASE_URI``
     - Database connection string (see :ref:`database-choice` below).
   * - ``ADMIN_PASSWORD``
     - Password for ``/admin``.
   * - ``PAGE_LIST``
     - The ordered sequence of pages participants see.

For the rest of the available settings — application options, admin options, security, completion codes, conditions, deployment — see :doc:`/reference/configuration`.

PAGE_LIST: defining the page sequence
-------------------------------------

``PAGE_LIST`` is the ordered list of pages a participant moves through. Each entry has a ``name`` (the human-readable label, shown in admin progress and breadcrumbs) and a ``path`` (the URL or page-type pattern):

.. code-block:: toml

   PAGE_LIST = [
       {name="Display Name", path="route/path"},
       {name="Another Page", path="different/route"}
   ]

**The first page** should be one of these participant-creation routes:

- ``consent`` — display ``consent.html``, create the participant on agreement, assign a condition.
- ``consent_nc`` — display ``consent.html``, create the participant on agreement, no condition assignment.
- ``create_participant`` — no consent screen displayed; create the participant immediately and assign a condition.
- ``create_participant_nc`` — no consent screen, no condition.

The four variants and when to pick which are covered in :doc:`consent`.

**The last page** must be ``end``. This shows the completion message and (if configured) generates a completion code participants can paste back into a recruitment platform.

**Page types between first and last:**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Path format
     - What it shows
   * - ``external_id``
     - A page asking the participant to enter their external ID (MTurk Worker ID, Prolific PID, etc.). Configurable via ``EXTERNAL_ID_LABEL`` and ``EXTERNAL_ID_PROMPT``.
   * - ``questionnaire/<name>``
     - The questionnaire from ``questionnaires/<name>.json``.
   * - ``questionnaire/<name>/<tag>``
     - The same questionnaire, recorded with a tag (used for repeated measures — see :ref:`repeated-questionnaires` below).
   * - ``instructions/<name>``
     - The HTML at ``templates/instructions/<name>.html``, wrapped in BOFS chrome with an automatic Continue button.
   * - ``simple/<name>``
     - The HTML at ``templates/simple/<name>.html``, wrapped in BOFS chrome but with no Continue button — you control navigation. See :doc:`your_own_pages`.
   * - ``custom/<name>``
     - The HTML at ``templates/custom/<name>.html``, served without BOFS chrome (no header, breadcrumbs, or styling). For embedded JS tasks.
   * - ``assign_condition``
     - Triggers condition assignment if the participant doesn't have one yet. Useful when consent was collected via ``consent_nc`` or ``create_participant_nc``.
   * - ``<blueprint_endpoint>``
     - A custom Python route from one of your blueprints. See :doc:`/framework/blueprints_routes`.

**A complete example:**

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",            path="consent"},
       {name="External ID",        path="external_id"},
       {name="Demographics",       path="questionnaire/demographics"},
       {name="Task Instructions",  path="instructions/task_intro"},
       {name="Practice Trials",    path="custom/practice_task"},
       {name="Main Task",          path="custom/main_task"},
       {name="Post-Task Survey",   path="questionnaire/post_task"},
       {name="Debrief",            path="simple/debrief"},
       {name="End",                path="end"}
   ]

For conditional routing (different page sequences per condition) and per-page ``show_if`` predicates, see :doc:`conditions_branching`.

.. _repeated-questionnaires:

Including the same questionnaire multiple times
-----------------------------------------------

Pre-test/post-test designs and longitudinal studies often need the same questionnaire administered more than once. Add it to ``PAGE_LIST`` multiple times with different ``tag`` values:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",      path="consent"},
       {name="Mood (pre)",   path="questionnaire/mood/pre"},
       {name="Task",         path="custom/task"},
       {name="Mood (post)",  path="questionnaire/mood/post"},
       {name="End",          path="end"}
   ]

Each tagged submission is stored as a separate row. Reading back a tagged response from a template or blueprint route uses ``participant.questionnaire("mood", "pre")`` and ``participant.questionnaire("mood", "post")``. See :doc:`/framework/participant_data` for the full API. Longitudinal studies that reuse questionnaires across separate sessions are covered in :doc:`longitudinal`.

Multiple config files
---------------------

A BOFS project isn't tied to a single ``config.toml``. Each ``.toml`` file is self-contained — its own settings, ``PAGE_LIST``, ``CONDITIONS``, database URI, port — and ``BOFS run`` takes the path to whichever one you want to load:

.. code-block:: bash

   BOFS run config.toml
   BOFS run pilot.toml -d
   BOFS run study_a.toml

Two common reasons to keep more than one:

- **Dev vs. production.** ``dev.toml`` for local work and ``config.toml`` for the deployed instance. ``PAGE_LIST``, ``CONDITIONS``, and questionnaire references usually match across both; what differs is ``PORT``, ``SQLALCHEMY_DATABASE_URI``, ``ADMIN_PASSWORD``, and ``BEHIND_REVERSE_PROXY``.
- **Multiple experiments in one project.** Separate studies that share the same custom pages, blueprints, or questionnaires can each have their own ``.toml`` with a different ``PAGE_LIST`` and database. Switch between them by passing a different file to ``BOFS run``.

.. _database-choice:

Choosing a database
-------------------

The ``SQLALCHEMY_DATABASE_URI`` setting tells BOFS which database to use:

**SQLite** is the recommended default: ``sqlite:///study.db``. It's a single-file database with no setup, and is good for development, piloting, and small or medium studies (i.e., dozens of concurrent users, not hundreds; the total participant count is not a factor).

If you need to handle a larger volume of participants, consider using PostgreSQL or MySQL. These can be hosted on a separate server to spread server load. BOFS uses SQLAlchemy to generate the database schema and interact with the database, so any database supported by SQLAlchemy is also supported by BOFS.

.. warning::

   Schema changes — adding fields to a questionnaire, adding columns to a custom table, adding new questionnaires — are applied at startup. With a fresh database (or one with no existing data), BOFS creates or alters the tables to match your JSON definitions. With existing participant data, schema changes can fail or quietly leave you with an inconsistent database. During development, the safest reset is to delete the SQLite ``.db`` file. With live data, see :doc:`/reference/questionnaire_properties` for the modification guide.

See also
--------

- The `minimal example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/minimal_example>`_ — the smallest workable ``PAGE_LIST``.
