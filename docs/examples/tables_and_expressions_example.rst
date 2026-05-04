Tables and Expressions Example
==============================

The ``tables_and_expressions_example`` project pairs a clicker task with a results screen that is rendered entirely from inline expressions in a questionnaire JSON file. There is no Python code in the project — everything that the participant sees on the results page is derived from JSONTable exports referenced through ``{{ ... }}`` placeholders.

The example is the canonical demonstration of four features that compose:

* **Bulk insert** to a JSONTable: the JS task captures every individual click as a row in a detail table (``clicks``: round, click index, time-since-round-start, x, y) and posts an entire round's clicks in a single POST to ``/table/clicks``.
* **Two tables in one task**: a separate summary table (``scores``: round, score) gets one row per round. This keeps the high/mean/total exports as straightforward scalar aggregates and the per-round dict from a ``group_by``.
* **Reading aggregates in a Jinja template**: a ``/instructions/results`` page iterates ``participant.table('scores').round_score`` to render a per-round score table with totals, side-by-side with per-round counts pulled from ``participant.table('clicks').round_clicks``.
* **Inline expressions in questionnaire JSON**: a follow-up reflection questionnaire uses ``{{ tables.scores.high_score }}`` and ``{{ tables.scores.round_score[1] }}``-style placeholders that resolve to the same numbers per participant at render time.

Source: ``tables_and_expressions_example/`` in the `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/tables_and_expressions_example>`_.

Running It
----------

From inside ``tables_and_expressions_example/`` after :doc:`installing BOFS </getting_started/installation>`:

.. code-block:: bash

    BOFS run tables_and_expressions.toml -d

The project listens on port 5006 by default; open http://localhost:5006 to step through the four pages — consent, instructions, the three-round click task, and the personalized results page. The admin panel is at http://localhost:5006/admin (password ``example``).

How the Pieces Fit Together
---------------------------

* ``tables/scores.json`` declares scalar exports (``high_score``, ``mean_score``, ``total_score``) plus a ``group_by`` export (``round_score``) keyed by ``round``.
* ``tables/clicks.json`` declares a scalar count export (``total_clicks``) and a per-round count (``round_clicks``).
* ``static/my_task.js`` runs the three rounds, captures each click into a JS array, and at end of round dispatches two HTTP requests in parallel: a list payload to ``/table/clicks`` and a single-row POST to ``/table/scores``.
* ``templates/instructions/results.html`` renders the per-round score table by iterating ``participant.table('scores').round_score.items()`` directly in Jinja.
* ``questionnaires/results.json`` writes the reflection questionnaire using ``{{ }}`` placeholders. The substitution layer handles the per-participant evaluation and HTML escapes the substituted values.

For the underlying reference material:

* The expression DSL and its subscript syntax are documented in :doc:`/advanced/expressions`.
* The substitution rules — what fields are walked, when escaping happens, what happens on errors — are documented under "Embedding values with ``{{ }}``" in :doc:`/advanced/advanced_questionnaires`.
* The bulk-insert format for JSONTables is documented in :doc:`/advanced/database_tables`.
