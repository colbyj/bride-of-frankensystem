The Database Layer
==================

BOFS uses `SQLAlchemy <https://www.sqlalchemy.org/>`_ — Python's standard ORM — for everything that touches the database: built-in tables (Participant, Progress, response rows), questionnaire-derived tables (one per JSON file), and custom tables (one per ``tables/*.json``). This page covers how those layers fit together and how to read or write from Python.

The exhaustive reference for custom-table JSON syntax (column types, exports, naming rules) is at :doc:`/reference/custom_tables`. This page is the conceptual orientation.

How BOFS uses SQLAlchemy
------------------------

A BOFS process holds one global ``db`` object, exposed as ``BOFS.globals.db``. It carries:

- The SQLAlchemy ``session`` — the unit-of-work used for queries, inserts, and commits.
- The model classes for built-in tables (``Participant``, ``Progress``, ``QuestionnaireInteraction``, ``ResponseLog``).
- One auto-generated model class per loaded questionnaire (named after the questionnaire file).
- One auto-generated model class per loaded custom table (named after the table JSON file).

Custom blueprint code reaches them by import:

.. code-block:: python

   from BOFS.globals import db
   from flask import session

   participant = db.Participant.query.get(session['participantID'])
   trials = db.trial_data.query.filter_by(participantID=session['participantID']).all()

Built-in models
---------------

Four SQLAlchemy models are part of BOFS itself, not derived from user JSON. They live in ``BOFS/default/models.py``.

- **Participant.** One row per consenting participant. Columns include ``participantID`` (PK), ``condition``, ``mTurkID``, ``timeStarted``, ``timeEnded``, ``finished``, ``code``. The ``Participant`` class also defines the methods used through the ``participant`` template variable — ``questionnaire()``, ``table()``, ``has_questionnaire()``, ``evaluate()``, ``display_duration()``. See :doc:`/reference/participant_data_api`.
- **Progress.** One row per page transition. Used by the admin panel to show timestamps for each page in a participant's flow.
- **QuestionnaireInteraction.** One row per UI event (focus, blur, change, paste, visibility) when ``LOG_QUESTIONNAIRE_INTERACTIONS = true``. For text fields, additional rows record per-input authenticity signals (keystroke counts, paste lengths, focus duration).
- **ResponseLog.** One row per consent submission, keyed to the participant.

You usually don't query these directly — the participant object's methods cover the common cases. Querying is appropriate when you're writing admin tooling or doing custom analytics.

Questionnaire-derived models
----------------------------

Each questionnaire JSON file produces a model class at startup. The class name matches the filename (without ``.json``), and the columns are derived from each question's ``id`` plus type:

- ``field`` and ``radiolist`` → ``String``
- ``num_field`` → ``Integer``
- ``checklist`` → ``Boolean`` (one column per option)
- ``radiogrid`` → ``Integer`` (one column per row)
- ``slider`` → ``Integer``
- ...and so on

Plus three columns added automatically: ``participantID`` (FK to ``Participant``), ``timeStarted``, ``timeEnded``, and ``tag`` for repeated submissions.

Reading from Python is the same as any SQLAlchemy model:

.. code-block:: python

   demographics_row = db.demographics.query.filter_by(
       participantID=session['participantID']
   ).first()

   age = demographics_row.age

The simpler ``participant.questionnaire('demographics').age`` does this lookup for you in one call. Use the raw SQLAlchemy query when you need filtering across all participants (e.g., for an admin tool).

Custom tables
-------------

Every ``tables/*.json`` file (at the project root or inside a blueprint) becomes a model class at startup. The columns come from the ``columns`` block in the JSON definition; the export-field aggregates come from the ``exports`` block. ``participantID`` and ``timeSubmitted`` are added automatically.

The :doc:`/reference/custom_tables` page covers the JSON format. The patterns most likely to come up in Python:

**Insert one row.**

.. code-block:: python

   row = db.trial_data()
   row.participantID = session['participantID']
   row.score = 42
   row.reaction_time = 312.5
   db.session.add(row)
   db.session.commit()

**Insert many rows efficiently.** ``db.session.add_all([...])`` plus a single commit:

.. code-block:: python

   rows = [
       db.trial_data(
           participantID=session['participantID'],
           score=score,
           reaction_time=rt,
       )
       for score, rt in zip(scores, rts)
   ]
   db.session.add_all(rows)
   db.session.commit()

**Query by participant.**

.. code-block:: python

   trials = db.trial_data.query.filter_by(
       participantID=session['participantID']
   ).order_by(db.trial_data.timeSubmitted).all()

**Aggregate in SQL.** Faster than iterating in Python for large tables:

.. code-block:: python

   from sqlalchemy import func

   avg_rt = db.session.query(
       func.avg(db.trial_data.reaction_time)
   ).filter_by(participantID=session['participantID']).scalar()

For most aggregations, declaring an ``exports`` block in the table JSON and accessing it via ``participant.table('trial_data').avg_rt`` is simpler — the SQL is generated for you and the result is cached on the accessor. Direct queries are appropriate for one-off or admin-only computations that don't fit cleanly into a per-participant export.

Calculated export fields in depth
---------------------------------

The ``exports`` block on a table is BOFS's way of defining per-participant aggregates without writing SQL. Each entry takes a ``fields`` dict (column-name → SQL expression) and optional ``filter``, ``group_by``, ``order_by``, and ``having`` keys:

.. code-block:: json

   {
     "columns": {
       "score": {"type": "integer"},
       "reaction_time": {"type": "float"},
       "block": {"type": "string"}
     },
     "exports": [
       {
         "fields": {
           "trial_count": "count(score)",
           "avg_rt": "avg(reaction_time)"
         }
       },
       {
         "filter": "block = 'practice'",
         "fields": {
           "practice_avg": "avg(score)"
         }
       },
       {
         "group_by": "block",
         "fields": {
           "block_avg": "avg(score)"
         }
       }
     ]
   }

At runtime, BOFS expands this into SQL queries scoped to each participant. The results appear three places:

1. As columns in the admin panel's per-participant CSV export.
2. As attributes on ``participant.table('trial_data')`` in templates and routes.
3. As reachable references in expressions (``tables.trial_data.avg_rt`` in a ``show_if`` predicate).

Full reference: :doc:`/reference/custom_tables`.

Showing table data in the participant detail view
-------------------------------------------------

The admin panel's per-participant page shows each page in the participant's flow with whatever data was submitted on that page. Questionnaire pages show responses automatically. Custom-page routes don't, by default — to surface data from a custom-page route, decorate the view with ``@page_tables('<table_name>')``:

.. code-block:: python

   from BOFS.util import page_tables

   @my_blueprint.route("/task")
   @verify_correct_page
   @verify_session_valid
   @page_tables('trial_data')
   def task():
       ...

The decorator can list multiple tables: ``@page_tables('trial_data', 'event_log')``. The participant detail page runs each table's calculated export fields scoped to the participant and displays the result inline. See :doc:`/reference/helper_functions`.

Custom SQLAlchemy models
------------------------

JSONTable handles the common case: one flat table per concept, scoped to participants, with simple aggregations on top. When that fits, it fits well — declarative, no Python required. When it doesn't, BOFS exposes the underlying SQLAlchemy directly through a ``models.py`` file in a blueprint.

This feature is for developers already comfortable with relational databases and SQLAlchemy. Researchers without that background usually do fine with JSONTable; the cases below are where ``models.py`` adds something the JSONTable shape can't:

- **Relationships between tables.** Foreign keys, one-to-many, many-to-many. JSONTable rows are flat per-participant logs; if you need a stimulus catalog joined to trial responses, that's a relationship.
- **Indexes and database-level constraints.** Compound indexes, unique constraints, check constraints.
- **Custom methods on the model.** Computed properties, validation logic, helper methods that operate on a row.
- **Mapping existing tables.** Reading from a database BOFS didn't create — for example, a stimulus pool that an external tool populates.

The factory pattern
~~~~~~~~~~~~~~~~~~~

A blueprint's ``models.py`` exports a ``create(db)`` function that returns one model class or a list of them. BOFS auto-discovers ``models.py`` alongside ``views.py``, calls ``create(db)`` at startup, and attaches each returned class to ``db`` so blueprint code can use it like any other model:

.. code-block:: python
   :caption: my_blueprint/models.py

   def create(db):
       class StimulusItem(db.Model):
           __tablename__ = 'stimulus_item'
           id = db.Column(db.Integer, primary_key=True)
           word = db.Column(db.String(64), nullable=False, index=True)
           category = db.Column(db.String(32), nullable=False)
           difficulty = db.Column(db.Float, default=0.5)

       class Trial(db.Model):
           __tablename__ = 'trial'
           id = db.Column(db.Integer, primary_key=True)
           participantID = db.Column(
               db.Integer, db.ForeignKey('participant.participantID'), nullable=False
           )
           stimulus_id = db.Column(
               db.Integer, db.ForeignKey('stimulus_item.id'), nullable=False
           )
           response = db.Column(db.String(64))
           reaction_time = db.Column(db.Float)

           stimulus = db.relationship('StimulusItem')

       return [StimulusItem, Trial]

The ``db.Model`` base, ``db.Column``, ``db.relationship``, and the type names (``db.Integer``, ``db.String``, etc.) are all standard `Flask-SQLAlchemy <https://flask-sqlalchemy.palletsprojects.com/>`_ — BOFS doesn't add a layer here, just hands you the configured ``db`` object.

After startup, the returned classes are available on ``db`` by class name:

.. code-block:: python
   :caption: my_blueprint/views.py

   @my_blueprint.route("/trial")
   @verify_correct_page
   @verify_session_valid
   def trial():
       item = db.session.query(db.StimulusItem).order_by(db.func.random()).first()

       trial = db.Trial(
           participantID=session['participantID'],
           stimulus_id=item.id,
       )
       db.session.add(trial)
       db.session.commit()

       return render_template("trial.html", word=item.word)

Schema creation and changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~

BOFS calls ``db.create_all()`` at startup, so a new model's table is created automatically the first time the project runs after ``models.py`` is added. Schema *changes* — adding a column, changing a type — are not applied automatically; that's the same trade-off as JSONTable. For changes after a project has live data, use `Alembic <https://alembic.sqlalchemy.org/>`_ or hand-written migration SQL.

Coexisting with JSONTable and questionnaires
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Three sources contribute models to the same ``db`` namespace and the same database:

- **Questionnaires.** Each ``questionnaires/<name>.json`` produces a model class named after the filename (``db.demographics`` from ``demographics.json``).
- **JSONTable.** Each ``tables/<name>.json`` produces a model class named after the filename (``db.trial_data`` from ``trial_data.json``).
- **Custom models.** Each class returned from a ``create(db)`` function in a ``models.py`` is attached to ``db`` under its class name.

Pick custom-model names that don't shadow a questionnaire or a JSONTable. ``class Demographics(db.Model)`` while ``questionnaires/demographics.json`` exists will collide on ``db.Demographics``/``db.demographics`` — case differs but the underlying database table name (set by ``__tablename__`` for custom models, or the filename for questionnaires/JSONTable) needs to be unique across all three.

A typical split: JSONTable for participant-generated data (trial responses, event logs), ``models.py`` for shared study-level data (stimulus pools, condition manifests, scoring rubrics) that participant data joins against. The two reference each other via foreign keys.

Limitations
~~~~~~~~~~~

- ``models.py`` must define a ``create(db)`` function.
- Models are loaded at startup. Adding a new model means restarting the project.
- The ``db.<ModelName>`` registration uses the class name, so two models with the same name across different blueprints will collide.

Switching from SQLite to PostgreSQL
-----------------------------------

For development, SQLite is built in and requires nothing. For production with many concurrent participants, PostgreSQL is the typical choice — it handles concurrent writers cleanly where SQLite serialises them.

The only change is the connection string in ``config.toml``:

.. code-block:: toml

   # Development:
   SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"

   # Production:
   SQLALCHEMY_DATABASE_URI = "postgresql://user:password@host:5432/dbname"

Schema creation runs at startup either way. Migrating live data between databases is a separate operation — typically a ``pg_dump``/``pg_restore`` after exporting the SQLite content with ``sqlalchemy``-native or third-party tools.

See :doc:`/deploying/server` for production deployment context.

See also
--------

- :doc:`/reference/custom_tables` — the JSON definition syntax, all column types, all export keys.
- :doc:`/reference/participant_data_api` — the methods on the ``Participant`` model.
- :doc:`/reference/helper_functions` — ``@page_tables`` and other decorators.
- :doc:`blueprints_routes` — the blueprint context for Python database access.
