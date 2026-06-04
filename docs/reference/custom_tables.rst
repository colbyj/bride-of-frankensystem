Custom Tables
=============

Custom tables let you record structured experiment data (trial responses, event logs, timing measurements) to the database outside the questionnaire system. A table is defined by a JSON file; BOFS creates the corresponding database table automatically at startup.

For a guided introduction to writing and reading data with custom tables, see :doc:`/building/storing_custom_data`.

Table Definition Files
----------------------

Place ``<name>.json`` files in the ``tables/`` directory at your project root, or inside a blueprint at ``<blueprint_name>/tables/``. The file name (without extension) becomes the table name used in routes and Python access.

See :doc:`/framework/blueprints_routes` for how blueprint-scoped tables are discovered.

Column Types
------------

Each column in the ``"columns"`` object specifies a ``"type"`` and an optional ``"default"``. Valid types are:

.. list-table::
   :header-rows: 1
   :widths: 15 20 65

   * - Type
     - SQLite storage
     - Notes
   * - ``integer``
     - ``INTEGER``
     - Default is ``0`` unless overridden.
   * - ``float``
     - ``NUMERIC``
     - Default is ``0`` unless overridden.
   * - ``boolean``
     - ``BOOLEAN``
     - Default is ``false`` unless overridden. Accepts ``true``/``false``, ``1``/``0``, ``"yes"``/``"no"``, ``"on"``/``"off"`` (case-insensitive) from form-encoded payloads.
   * - ``string``
     - ``TEXT``
     - Default type when ``"type"`` is absent. Default value is ``""`` unless overridden.
   * - ``datetime``
     - ``DATETIME``
     - No ``"default"`` is accepted; the column defaults to ``datetime.min``. Send ISO 8601 strings from JavaScript.
   * - ``json``
     - ``TEXT``
     - No ``"default"`` is accepted; the column defaults to ``NULL``. Stores arrays, objects, or any JSON-serialisable structure. The HTTP API serialises and deserialises transparently — JavaScript always receives a native object or array.

Example Table with All Column Types
------------------------------------

.. code-block:: json

    {
      "columns": {
        "integer_column": {
          "type": "integer",
          "default": 0
        },
        "float_column": {
          "type": "float",
          "default": 0
        },
        "boolean_column": {
          "type": "boolean",
          "default": true
        },
        "string_column": {
          "default": "this is a test"
        },
        "datetime_column": {
          "type": "datetime"
        },
        "json_column": {
          "type": "json"
        }
      }
    }

Auto-added Columns
------------------

Every custom table automatically receives two additional columns that you do not declare and should not include in POST payloads:

- ``participantID`` — foreign key to the ``participant`` table, populated from the current session.
- ``timeSubmitted`` — ``DATETIME``, set to the server's current UTC time on each insert.

When the table is routed to a non-default database via the ``"database"`` field (see below), ``participantID`` is a plain indexed integer column rather than a foreign key, since SQLAlchemy can't enforce a FK across separate engines.

Routing a Table to a Different Database
---------------------------------------

A custom table can write to a database other than the project's main one. Add a top-level ``"database"`` field naming an entry from ``[SQLALCHEMY_BINDS]`` in ``config.toml``:

.. code-block:: json

   {
     "database": "pii",
     "columns": {
       "follow_up_email": {"type": "string"}
     }
   }

The same option is available on questionnaire JSON files. Trade-offs and the per-bind admin export endpoint are covered in :doc:`/framework/database_layer`.

Naming Rules
------------

Column names and export field names must be valid Python identifiers: they must start with a letter or underscore and contain only letters, digits, and underscores. Python keywords (``class``, ``return``, ``for``, etc.) are not allowed.

Within a single table, no export field name may duplicate a column name. The ``TableAccessor`` (returned by ``participant.table('name')``) resolves attribute access to exports; a collision would shadow the raw column.

Calculated Export Fields
------------------------

The ``"exports"`` block defines per-participant aggregations that appear as columns on the admin panel's Export page and as attributes on the ``TableAccessor``. Each entry in the array is a single export definition.

Export Object Keys
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Key
     - Required
     - Description
   * - ``fields``
     - Yes
     - A dict mapping output column names to SQL expressions. Values may be bare column names (``"my_column"``) or aggregate expressions (``"sum(my_column)"``). When there is more than one row per participant, include an aggregate function (``MIN``, ``MAX``, ``SUM``, ``COUNT``, or ``AVG``).
   * - ``filter``
     - No
     - A SQL ``WHERE`` expression restricting which rows are included (e.g. ``"my_column > 1"`` or ``"levelName IN ('Intro1', 'Intro2')"``) .
   * - ``group_by``
     - No
     - A column name (string) or list of column names to group by. Each unique value in the grouped column produces a separate result. In the data export each level appears as a suffixed column (``<field>_<level>``). In templates, a ``group_by`` export returns a dict keyed by group value rather than a scalar.
   * - ``order_by``
     - No
     - A SQL ``ORDER BY`` expression controlling the column order in the data export.
   * - ``having``
     - No
     - A SQL ``HAVING`` expression. Only valid when ``group_by`` is also present.

Simple Example
~~~~~~~~~~~~~~

A table that stores numbers entered by participants and exports a count per participant:

.. code-block:: json

    {
      "columns": {
        "your_number": {"type": "integer"}
      },
      "exports": [
        {
          "fields": {"total_numbers": "count(your_number)"}
        }
      ]
    }

Complex Example
~~~~~~~~~~~~~~~

A game-progress table with multiple export definitions, including a ``group_by`` over session name:

.. code-block:: json

    {
      "columns": {
        "finishedLevel": {"type": "integer"},
        "levelName": {},
        "deathCount": {"type": "integer"},
        "levelTime": {"type": "float"},
        "sessionName": {}
      },
      "exports": [
        {
          "group_by": "sessionName",
          "order_by": "sessionName",
          "fields": {
            "totalLevelsFinished": "sum(finishedLevel = 'True')",
            "totalDeathCount": "sum(deathCount)"
          }
        },
        {
          "filter": "levelName IN ('Intro1', 'Intro2', 'Intro3')",
          "fields": {
            "tutorialLevelsTime": "sum(levelTime)",
            "tutorialLevelsCompleted": "sum(finishedLevel = 'True')"
          }
        }
      ]
    }

Reading Export Values from Templates
-------------------------------------

Each scalar (non-``group_by``) export field is accessible as an attribute on the ``TableAccessor`` returned by ``participant.table('name')``:

.. code-block:: html+jinja

    {% set trials = participant.table('cognitive_task') %}
    <p>Total trials: {{ trials.totalLevelsFinished }}</p>

The aggregate runs scoped to the current participant. All computed values are memoised on the accessor instance.

``group_by`` exports return a dict keyed by group value (or a tuple of values when ``group_by`` is a list). Access a specific level by subscript:

.. code-block:: html+jinja

    {% set trials = participant.table('game_progress') %}
    <p>Deaths in session A: {{ trials.totalDeathCount['session_a'] }}</p>

To iterate all levels:

.. code-block:: html+jinja

    {% for session, deaths in trials.exports['totalDeathCount'].items() %}
      <p>{{ session }}: {{ deaths }}</p>
    {% endfor %}

In the CSV data export, each level appears as a separate suffixed column (``totalDeathCount_session_a``, ``totalDeathCount_session_b``, etc.).

For ``show_if`` predicates and ``participant.evaluate()``, scalar export fields are reachable via the ``tables.<name>.<column>`` reference form. See :doc:`/reference/expressions` for expression syntax.

For raw row access, iterate ``participant.table('name')`` directly or use ``participant.table('name').rows``. The accessor proxies ``__iter__``, ``__len__``, and ``__getitem__`` to ``rows``.

Writing Data from JavaScript
-----------------------------

POST to ``/table/<name>`` to insert one or more rows. The server attaches ``participantID`` and ``timeSubmitted`` from the session — do not include those fields in the payload.

See :doc:`/reference/built_in_routes` for the full route reference.

Single Row — JSON
~~~~~~~~~~~~~~~~~

.. code-block:: javascript

    fetch('/table/my_task', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({score: 42, label: 'correct'})
    });

On success the endpoint returns ``204 No Content``. On a validation error it returns ``400 Bad Request``.

Batch Insert — JSON Array
~~~~~~~~~~~~~~~~~~~~~~~~~

Send a JSON array to insert multiple rows in a single request. All rows are committed together; if any row is malformed the entire batch is rolled back and ``400`` is returned.

.. code-block:: javascript

    const trials = [
        {trial: 1, rt: 312, response: 'left'},
        {trial: 2, rt: 498, response: 'right'},
        {trial: 3, rt: 271, response: 'left'},
    ];

    fetch('/table/my_task', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(trials)
    });

Single Row — Form-encoded
~~~~~~~~~~~~~~~~~~~~~~~~~

Form-encoded POSTs are accepted for compatibility with HTML forms or older code. Batch inserts are not supported in this mode.

.. code-block:: javascript

    fetch('/table/my_task', {
        method: 'POST',
        body: new URLSearchParams({score: 42, label: 'correct'})
    });

Storing Structured Data in a ``json`` Column
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pass a JavaScript object or array directly in the JSON payload — the server serialises it automatically:

.. code-block:: javascript

    const mouseTrajectory = [
        {t: 0,  x: 512, y: 300},
        {t: 16, x: 510, y: 298},
        {t: 32, x: 505, y: 290},
    ];

    fetch('/table/my_task', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({trial: 1, trajectory: mouseTrajectory})
    });

When the row is retrieved via GET, ``trajectory`` is already a JavaScript array — no client-side ``JSON.parse`` is needed.

Reading Data from JavaScript
-----------------------------

A GET request to ``/table/<name>`` returns a JSON array of all rows belonging to the current participant.

.. code-block:: javascript

    fetch('/table/my_task')
        .then(r => r.json())
        .then(rows => {
            // rows is an array of objects, e.g. [{trial: 1, score: 42}, ...]
            console.log(rows);
        });

Query-string parameters are applied as exact-match filters. The comparison is string-cast, so this is best suited to integer or string columns with known discrete values:

.. code-block:: javascript

    // Retrieve only rows where score equals 42
    fetch('/table/my_task?score=42')
        .then(r => r.json())
        .then(rows => console.log(rows));

.. note::

   Query-string filters use string-cast equality (``CAST(column AS TEXT) = 'value'``). Range queries and other filtering must be done in Python or post-processed on the client.

Accessing Tables from Python
-----------------------------

Import ``db`` from ``BOFS.globals`` to access SQLAlchemy sessions and dynamically created table classes.

.. code-block:: python

    from BOFS.globals import db

Custom table classes are registered on the ``db`` object by the table file name. For example, a table defined in ``tables/answers.json`` is accessible as ``db.answers``.

Querying
~~~~~~~~

Use ``db.session.query`` with standard SQLAlchemy ORM patterns:

.. code-block:: python

    # All rows for participants who completed the experiment
    rows = db.session.query(db.answers).filter(
        db.answers.participantID == participant_id
    ).all()

See the `SQLAlchemy ORM querying documentation <https://docs.sqlalchemy.org/en/20/orm/queryguide/>`__ for the full query API. For database internals and session management, see :doc:`/framework/database_layer`.

Inserting
~~~~~~~~~

Create an instance of the table class, set attributes, then add and commit:

.. code-block:: python

    from flask import session

    entry = db.answers()
    entry.participantID = session['participantID']
    entry.answer = request.form['answer']

    db.session.add(entry)
    db.session.commit()

``timeSubmitted`` is populated automatically by its column default and does not need to be set.
