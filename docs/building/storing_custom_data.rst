Storing Custom Data
===================

Questionnaire responses are stored automatically — BOFS creates the database columns from your question IDs and writes each submission for you. Task data (trial results, reaction times, event logs) doesn't have that automatic path. Custom tables give it one.

A custom table is a JSON file that describes the columns you want. BOFS creates the corresponding database table at startup and exposes an HTTP endpoint your JavaScript can POST to.

Defining a Table
----------------

Place a ``<name>.json`` file in the ``tables/`` directory at your project root. The file name (without the ``.json`` extension) becomes the table name used in routes and Python access.

.. code-block:: text

   my_study/
   ├── config.toml
   ├── tables/
   │   └── trials.json
   └── questionnaires/

Tables can also live inside a blueprint at ``<blueprint_name>/tables/``. See :doc:`/framework/blueprints_routes` for how blueprint-scoped tables are discovered.

Column Types
~~~~~~~~~~~~

Each entry in the ``"columns"`` object is one column. Valid types are ``integer``, ``float``, ``boolean``, ``string``, ``datetime``, and ``json``. If ``"type"`` is omitted, the column defaults to ``string``.

A minimal table for a reaction-time task:

.. code-block:: json

    {
      "columns": {
        "score": {"type": "integer", "default": 0},
        "reaction_time": {"type": "float", "default": 0}
      }
    }

Save this as ``tables/trials.json`` and BOFS creates the table the next time the project starts.

Two columns are added automatically to every custom table and should not appear in your file or in POST payloads:

- ``participantID`` — links the row to the participant who submitted it.
- ``timeSubmitted`` — the server's UTC time at the moment of insert.

The full list of column types, default-value rules, and naming constraints is in :doc:`/reference/custom_tables`.

Writing Data from JavaScript
-----------------------------

POST a JSON object to ``/table/<name>`` from your task code. The server attaches ``participantID`` and ``timeSubmitted`` automatically.

.. code-block:: javascript

    fetch('/table/trials', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({score: 42, reaction_time: 312.5})
    });

On success the endpoint returns ``204 No Content``. On a validation error it returns ``400 Bad Request``.

The ``"json"`` column type accepts a JavaScript object or array directly in the payload — useful for per-trial event logs, mouse trajectories, or keystroke timings where a flat column per measurement would be impractical:

.. code-block:: javascript

    fetch('/table/trials', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            score: 42,
            events: [{t: 0, x: 512, y: 300}, {t: 16, x: 510, y: 298}]
        })
    });

When you later read the row back, ``events`` is already a JavaScript array — no ``JSON.parse`` needed.

For sending multiple rows in one request (batch insert) and for form-encoded POSTs, see :doc:`/reference/custom_tables`.

Reading Data Back
-----------------

A GET request to ``/table/<name>`` returns a JSON array of all rows belonging to the current participant:

.. code-block:: javascript

    fetch('/table/trials')
        .then(r => r.json())
        .then(rows => {
            // rows is an array of objects, e.g. [{score: 42, reaction_time: 312.5}, ...]
            console.log(rows);
        });

Query-string parameters are applied as exact-match filters:

.. code-block:: javascript

    fetch('/table/trials?score=42')
        .then(r => r.json())
        .then(rows => console.log(rows));

.. note::

   Query-string filters use string-cast equality. Range queries and more complex filtering must be done in Python or post-processed on the client.

Calculated Export Fields
-------------------------

The admin panel's per-table CSV export gives you raw rows. Calculated export fields let you define per-participant aggregations alongside the table itself. Once defined, they appear as columns on the admin **Export** page (see :doc:`/building/monitoring_data`) and are accessible from Jinja2 templates.

Add an ``"exports"`` block to the table's JSON file. Each entry in the array defines one set of fields using a SQL aggregate expression:

.. code-block:: json

    {
      "columns": {
        "score": {"type": "integer"},
        "reaction_time": {"type": "float"}
      },
      "exports": [
        {
          "fields": {
            "trial_count": "count(score)",
            "avg_rt": "avg(reaction_time)"
          }
        }
      ]
    }

The supported aggregate functions are ``MIN``, ``MAX``, ``SUM``, ``COUNT``, and ``AVG``. Optional ``filter``, ``group_by``, ``order_by``, and ``having`` keys are available for more complex exports.

Calculated fields are reachable in templates via the ``TableAccessor``:

.. code-block:: html+jinja

    {% set trials = participant.table('trials') %}
    <p>Trials completed: {{ trials.trial_count }}</p>
    <p>Average RT: {{ trials.avg_rt }}</p>

Scalar export fields are also reachable in ``show_if`` predicates via the ``tables.<name>.<column>`` reference form. See :doc:`/reference/expressions` for expression syntax.

The complete reference — all export keys, ``group_by`` behaviour, the ``@page_tables`` decorator for the participant detail view, and the Python ``db`` API — is in :doc:`/reference/custom_tables`.

Further Reading
---------------

- :doc:`/reference/custom_tables` — all column types, export keys, naming rules, batch inserts, Python API, and the ``@page_tables`` decorator.
- :doc:`/reference/expressions` — ``tables.<name>.<column>`` reference form for ``show_if`` and ``participant.evaluate()``.
- :doc:`/framework/database_layer` — SQLAlchemy session and model details.
- :doc:`/building/monitoring_data` — admin export panel.
