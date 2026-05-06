Quickstart: Integrating a Custom Task
=====================================

The previous page got you to a working survey. This page is a tour of what BOFS can do beyond surveys — the patterns for embedding a JavaScript task, storing data the task generates, and stitching it into the page flow.

There's no step-by-step build here; the goal is to show you the shape of a custom-task project so you can pick the example that fits what you're trying to build and read the source.

The general pattern
-------------------

A custom task in BOFS is three pieces:

- **A custom page** that hosts the task's HTML and JavaScript. BOFS serves your HTML from the project's ``templates/`` directory, and any static assets (libraries, images) from the project's ``static/``.
- **A custom database table** that gives the task a place to write its data. You define the table in a small JSON file; BOFS creates the underlying SQL table at startup. The task POSTs to ``/table/<name>`` and the row appears in the database.
- **A** ``PAGE_LIST`` **entry** that puts the task page in sequence with consent, instructions, post-task questionnaires, and the end page.

The same three pieces compose for any in-browser task — p5.js sketches, jsPsych or lab.js trial sequences, Unity WebGL builds, raw vanilla JS. What changes is which library you load and what the per-trial data looks like.

The p5.js example
-----------------

``p5_example`` (in the `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples>`_) is the smallest illustration. The participant clicks as many times as they can in five seconds; the score gets posted to a custom table; the next page advances automatically.

**The task page** lives under ``templates/simple/my_task.html`` and is two script tags plus a ``<main>`` for p5 to attach a canvas to:

.. code-block:: html

   <script src="/static/p5.min.js"></script>
   <script src="/static/my_task.js"></script>
   <main></main>

Files in ``templates/simple/`` are served at ``/simple/<filename>`` (no ``.html``), so this is reachable at ``/simple/my_task``. The page is wrapped in BOFS's standard header, breadcrumbs, and styling — to drop the chrome (typical for fullscreen tasks), use ``templates/custom/`` instead, served at ``/custom/<filename>``.

**The task script** in ``static/my_task.js`` runs the click counter and, after five seconds, POSTs the result and advances:

.. code-block:: javascript

   $.post("/table/my_task", { score: score }, function () {
       window.location.href = "/redirect_next_page";
   });

``/table/my_task`` is a built-in route that writes the posted data into the ``my_task`` custom table. ``/redirect_next_page`` is also built-in: it looks up the participant's current position in ``PAGE_LIST`` and sends them to whatever comes next, so you don't hard-code the URL of the page after the task.

**The table definition** in ``tables/my_task.json`` declares one column and two derived aggregates:

.. code-block:: json

   {
     "columns": {
       "score": { "type": "integer", "default": 0 }
     },
     "exports": [
       {
         "fields": {
           "average_score": "avg(score)",
           "high_score": "max(score)"
         }
       }
     ]
   }

BOFS creates the ``my_task`` table at startup. The export aggregates show up per-participant in the admin export and are also addressable from page-level ``show_if`` predicates as ``tables.my_task.average_score`` and ``tables.my_task.high_score``.

``PAGE_LIST`` ties consent, instructions, the task, and the end page together:

.. code-block:: toml

   PAGE_LIST = [
       {name='Consent', path='consent'},
       {name='Instructions', path='instructions/task_instructions'},
       {name='Task', path='simple/my_task'},
       {name='End', path='end'}
   ]

That's the entire integration. No Python.

Other integration patterns
--------------------------

The example repository covers four more shapes of custom task. The PAGE_LIST and questionnaire layout are similar across them; what differs is which JavaScript library runs the trials and what the per-trial data looks like.

- **jsPsych** — the `jspsych_example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/jspsych_example>`_ runs a Stroop task with `jsPsych <https://www.jspsych.org/>`_. Trial timing and key capture are handled by jsPsych; BOFS handles questionnaires, condition assignment, and storage. Per-trial data is POSTed in a single batch to ``/table/jspsych_trials``. The jsPsych library is vendored under ``static/jspsych/`` so the example runs offline.

- **lab.js** — the `labjs_example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/labjs_example>`_ is the parallel of the jsPsych example with `lab.js <https://lab.js.org/>`_ instead. The ``PAGE_LIST`` and questionnaires are identical; only the trial-running framework and the per-trial data shape change.

- **Unity WebGL** — the `unity_example_2021.1 <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/unity_example_2021.1>`_ and `unity_example_2023.2 <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/unity_example_2023.2>`_ projects host a Unity WebGL build inside a BOFS page. They demonstrate three layouts (BOFS-chrome, fullscreen, fully custom), pushing the participant ID into the running build, reading the assigned condition from inside Unity, posting data back to a custom table, and advancing the BOFS page flow from within Unity.

- **Embedded media** — the `embedding_media_example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/embedding_media_example>`_ shows every place BOFS can embed an image or video: in custom HTML, in questionnaire ``instructions`` fields, in ``textview`` questions, and as their own ``video`` question with optional "force watch" enforcement.

Where to learn more
-------------------

To build the rest of an experiment around your task:

- :doc:`/building/adding_survey_questions` — pre/post-task questionnaires, question types, conditional questions.
- :doc:`/building/page_flow` — adding pages, repeating questionnaires with different ``tag`` values, using multiple ``.toml`` files for dev/production splits or running several experiments out of one project.
- :doc:`/building/conditions_branching` — A/B and multi-arm experiments, conditional routing, page-level ``show_if``.
- :doc:`/building/storing_custom_data` — going deeper on custom tables, including JS read/write and Python access.
- :doc:`/building/monitoring_data` — admin panel, exports, results.

If you want to write Python on top of BOFS — custom routes, server-side stimulus generation, complex data processing — see :doc:`/framework/architecture` and :doc:`/framework/blueprints_routes`.
