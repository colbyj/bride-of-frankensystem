Custom Database Tables (Models)
===============================

If you need to record your own data to the database, then you can do so by defining custom database tables. Tables can
be placed within the ``/tables`` directory of your project or within a blueprint at ``/<blueprint_name>/tables``.

Column Types
------------

Tables are made up of columns. Each column can have its own data type. Possible data types are ``integer``, ``float``,
``boolean``, or ``string``.

Like questionnaires, tables are defined in JSON format. Below is an example of a table with every different possible
type of data. Notice that each column has a "default" value; this entry can be omitted if not required. Additionally,
notice that if a "type" is not specified, then it defaults to being a string.

.. code-block:: JSON

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
        }
      }
    }


Calculated Export Fields
------------------------

The admin panel's per-table CSV export gives you the raw rows of a custom table. That's enough for some studies, but it doesn't include participant-level information like the assigned condition, and aggregating across rows (totals per participant, summary stats, repeated-measures pivots) has to happen after the export.

Calculated exports let you define those aggregations alongside the table itself. Once defined, the calculated fields appear in the participant-level export on the admin panel's "Export" page, in wide format. The expressions use SQL syntax — if it's been a while, the `SQLite tutorial <https://www.sqlitetutorial.net/>`_ is a good refresher.

Add an ``"exports"`` entry to the table's JSON file:

.. code-block:: JSON

    {
      "columns": {},
      "exports": []
    }

The most simple exports will simply be use a ``MIN``, ``MAX``, ``SUM``, ``COUNT``, or ``AVG`` aggregate function to
calculate the minimum, maximum, sum, count, or average of the entries. For example, the on table defined below, numbers
entered by the user can be stored in a table and the calculated field reports a count of the numbers entered for each
user.

.. code-block:: JSON

    {
      "columns": {
        "your_number": {"type": "integer"}
      },
      "exports": [
        {
          "fields" : {"total_numbers": "count(your_number)"}
        }
      ]
    }

Each export supports the following keys:

.. table:: JSON keys for tables
    :widths: 20,65

    ==================== =============
    Key                  Description
    ==================== =============
    fields (required)    A dictionary of fields to export. This dictionary's keys are the names you want for your column, and the values are the data you want to export. This data can be the database table's column names (e.g., my_column) or column expressions (e.g., sum(my_column)). Note: you will want to include an aggregate function in your field's definition (MIN, MAX, SUM, COUNT, or AVG) unless there is only one row in your table per each participant.
    filter (optional)    This is a SQL WHERE expression. This can be used to omit rows from the table that are not of interest (e.g., my_column > 1 or my_column != 'text').
    group_by (optional)  This a SQL GROUP BY expression. If the table you are exporting from has groups of repeated measures that you want to analyze separately then you will need to make use of this. Each unique entry in the grouped column will have a corresponding column in the export. For example, if you had participants complete a task over multiple days, you could group by day and you will end up with a column for each day (e.g., monday_my_column, tuesday_my_column, etc.). It is also possible to group by multiple columns by specifying a list of column names (each a string).
    order_by (optional)  This is a SQL ORDER BY expression. It determines the order of the columns in the export.
    having (optional)    This a SQL HAVING expression. It can only be used if group_by is used.
    ==================== =============

Let's consider a more complicated example. In this example, there are 5 columns, two integers, one float, and two
strings. What is being measured is progress within a game, with one entry in the table being one level. Multiple
sessions of the game were played, and each had a unique name. The data being exported is the total levels finished over
each play session, the total deaths for each play session, the time taken to complete three intro levels, and the count
of of three intro levels completed.

.. code-block:: JSON

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


Accessing Tables from Python
----------------------------

From your python code, import ``db`` from ``BOFS.globals``.

.. code-block:: python

    from BOFS.globals import db


The ``db`` object provides access to all database-related functionality.


Reading Data
~~~~~~~~~~~~

Queries can be completed by using ``db.session``. Refer to the SQLAlchemy documentation on `using the session <http://docs.sqlalchemy.org/en/rel_0_9/orm/session.html>`_.

**Example:** Getting a list of all participants who have finished the experiment.

.. code-block:: python

    finished_participants = db.session.query(db.Participant).filter(db.Participant.finished == True).all()


See the SQLAlchemy documentation on `querying with the ORM <https://docs.sqlalchemy.org/en/13/orm/tutorial.html#querying>`_.
for more details.

Inserting Data
~~~~~~~~~~~~~~
Using SQLAlchemy you create new database rows by creating new instances of your model classes. You then set your
attributes, indicate to the session that you want to add a new row, and commit your changes.

For example:

.. code-block:: python

        log = db.answers()  # This database table was defined in /advanced_example/tables/answers.json
        log.participantID = session['participantID']
        log.answer = request.form['answer']

        db.session.add(log)
        db.session.commit()

See the SQLAlchemy documentation on `adding and updating objects <https://docs.sqlalchemy.org/en/13/orm/tutorial.html#querying>`_
for more details.