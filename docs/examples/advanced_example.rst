Advanced Example
================

The ``advanced_example`` project exercises most BOFS features in a single runnable study. It's the right thing to look at once you've understood the :doc:`/getting_started/quickstart_existing` and want to see how the larger pieces fit together.

Source: ``advanced_example/`` in the `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/advanced_example>`_.

What It Demonstrates
--------------------

* **Two experimental conditions** with balanced random assignment (``CONDITIONS``).
* **Conditional routing** — the order of two questionnaires flips depending on which condition the participant is in (``conditional_routing`` inside ``PAGE_LIST``).
* **A custom blueprint** (``my_blueprint/``) with its own ``views.py``, templates, and static files, registering a ``/task`` route the participants pass through.
* **Session-validation decorators** (``@verify_correct_page``, ``@verify_session_valid``) protecting the custom route.
* **A custom database table** defined by JSON (``my_blueprint/tables/`` and project-level ``tables/``), with form data posted from the task being written to it.
* **Three questionnaires** (``example.json``, ``grid.json``, ``variables.json``) showing different question types, including radio grids and slider scales, plus per-questionnaire calculations.
* **External ID collection** via the ``external_id`` page.
* **A static completion code** shown on the end page (``STATIC_COMPLETION_CODE``).
* **Session resumption** — ``RETRIEVE_SESSIONS = true`` lets a participant who left mid-experiment return with the same external ID and pick up where they left off.

Running It
----------

From inside ``advanced_example/`` after :doc:`installing BOFS </getting_started/installation>`:

.. code-block:: bash

    BOFS run advanced.toml -d

The project listens on port 5004 by default. Open http://localhost:5004 to step through the experiment, or http://localhost:5004/admin (password ``example``) to inspect participant progress and export data.
