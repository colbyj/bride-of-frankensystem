A/B Experiment Example
======================

A two-condition between-subjects study: each participant is randomly assigned to either a Linear Menu or a Marking Menu and only sees the instructions and task for that condition. The smallest example in the repository that exercises ``CONDITIONS`` and ``conditional_routing``.

Source: ``ab_experiment/`` in the `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/ab_experiment>`_.

What It Demonstrates
--------------------

* **Two conditions with balanced random assignment** (``CONDITIONS``). BOFS's greedy balancer keeps the split close to 50/50 over the course of a run.
* **Conditional routing** — a ``conditional_routing`` block inside ``PAGE_LIST`` sends each participant to the instructions and task page that match their assigned condition.
* **Condition-specific instruction templates** in ``templates/instructions/``, one per condition.
* **A custom blueprint** (``menu_task/``) with one Flask route per condition, registered in the page list. The shared task template branches on the ``technique`` parameter to load the correct menu component.
* **Per-trial logging via a JSONTable** (``menu_task/tables/menu_trials.json``) including a ``json``-typed ``trajectory`` column for raw mouse samples.
* **Calculated export fields** so per-participant accuracy and response-time summaries appear directly in the admin export.
* **Session-validation decorators** (``@verify_correct_page``, ``@verify_session_valid``) protecting the custom routes.

The interactive task itself (a D3-based menu component plus a small JS trial runner) is shared with the longitudinal example in the same repository; the difference here is the surrounding scaffolding, which is single-session and minimal.

For the underlying mechanics — how conditions are defined, how the balancer works, how ``conditional_routing`` expands at render time — see the conditional-routing section of :doc:`/getting_started/project_configuration`. For the JSONTable schema, see :doc:`/advanced/database_tables`.

Running It
----------

From inside ``ab_experiment/`` after :doc:`installing BOFS </getting_started/installation>`:

.. code-block:: bash

    BOFS run ab_experiment.toml -d

The project listens on port 5005 by default. Open http://localhost:5005 to step through the experiment, or http://localhost:5005/admin (password ``example``) to inspect participant progress and export data.
