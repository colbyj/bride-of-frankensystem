Tutorial: Integrating a JavaScript Task
=======================================

This tutorial walks through embedding a custom JavaScript task inside a BOFS project. It introduces two features that the quickstart didn't touch: :doc:`blueprints </advanced/advanced_custom_pages>`, which let you add your own pages to a project, and :doc:`custom database tables </advanced/database_tables>`, which give your task a place to store its data.

The finished version of this project is the :doc:`p5_example </examples/p5_example>` in the BOFS examples repository — feel free to read along with the source there if you'd rather not type everything out.

Prerequisites
-------------

This tutorial assumes you've already worked through :doc:`quickstart_create` and have BOFS installed (see :doc:`installation`). The quickstart covers the ``BOFS init`` wizard, the role of ``config.toml``, the ``PAGE_LIST`` setting, and the basic project layout — all of which this tutorial builds on without re-explaining.

Bootstrapping ``p5_example``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you'd rather skip ahead and bootstrap a fresh project, here's the bare minimum:

1. Run ``BOFS init``.
2. When prompted for the project name, enter ``p5_example``.
3. Leave **all** optional features unchecked — this tutorial replaces them with its own consent text, instructions, task page, and (custom) database table.
4. Decline the "start the project now" prompt at the end.

That gives you a ``p5_example/`` directory containing a ``config.toml``, a placeholder ``consent.html``, and an empty ``templates/`` tree. The rest of this tutorial layers a custom blueprint on top, replaces ``consent.html`` with a placeholder of its own, and swaps ``config.toml`` for a tutorial-specific ``p5_example.toml`` (you can either rename the wizard's ``config.toml`` or use whichever filename you prefer when you run the project — ``BOFS run`` takes the path as an argument).

Project Layout
--------------

The bootstrap above gives you the project root. The tutorial adds a custom blueprint called ``my_task/`` with the following subdirectories:

* ``my_task/`` — root directory for the blueprint.
* ``my_task/static/`` — static files served by the blueprint, such as ``.js`` files.
* ``my_task/tables/`` — custom database table definition (a ``.json`` file).
* ``my_task/templates/`` — template files (``.html``).
* ``my_task/templates/instructions/`` — instruction page(s).
* ``my_task/templates/simple/`` — HTML for the task itself.

By the end you'll have these files:

.. figure:: /examples/p5_example/p5_example_files.png
  :alt: The files you'll have in those directories at the end of the tutorial.

  Final file layout.

Python Code (``views.py``)
--------------------------

For more involved blueprints you'd add a ``views.py`` (see :doc:`/advanced/advanced_custom_pages`). This example doesn't need one — BOFS's built-in routes cover everything we need.

The Task (``my_task.js``)
-------------------------

The JavaScript task uses the `p5.js <https://p5js.org/>`_ library. Place a copy of ``p5.min.js`` in ``/p5_example/my_task/static/`` (download it from the p5.js site) alongside this file:

.. code-block:: javascript
    :caption: /p5_example/my_task/static/my_task.js

    let score = 0;

    function setup() {
        createCanvas(720, 400);
    }

    function draw() {
        background(230);
        text('score is ' + score, 100, 100);
    }

    function mousePressed() {
        score += 1;
    }

    // After 5 seconds, send the score back and advance to the next page.
    setTimeout(function () {
        let dataToSend = {
            score: score
        };

        $.post("/table/my_task", dataToSend, function () {
            window.location.href = "/redirect_next_page"
        });
    }, 5000);

Two BOFS-specific things to notice:

* The ``$.post`` target ``/table/my_task`` is a built-in BOFS route. It writes the posted form data into a custom table called ``my_task`` — provided we define one in the next step.
* ``/redirect_next_page`` is also built-in. It looks up where the participant currently is in ``PAGE_LIST`` and sends them to whatever comes next, so you don't have to hard-code the URL of the next page.

The Table (``my_task.json``)
----------------------------

The custom table is described by a JSON file matching the schema in :doc:`/advanced/database_tables`:

.. code-block:: json
    :caption: /p5_example/my_task/tables/my_task.json

    {
      "columns": {
        "score": {
          "type": "integer",
          "default": 0
        }
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

This defines one column (``score``, integer, defaulting to ``0``) and two SQL-derived export fields — ``average_score`` and ``high_score``. In this project each participant only ever submits one score, so those aggregates are a bit redundant in practice, but they show how the export hooks work.

Including this file gives BOFS enough information to create a ``my_task`` table at startup:

.. figure:: /examples/p5_example/p5_example_tables.png
  :alt: A listing of the database tables now included in the project.

  Database tables after adding the ``my_task`` table.

The View (``my_task.html``)
---------------------------

A small HTML file pulls the p5 library and our task script into the page:

.. code-block:: html
    :caption: /p5_example/my_task/templates/simple/my_task.html

    <script src="/my_task/p5.min.js"></script>
    <script src="/my_task/my_task.js"></script>
    <main></main>

The ``<main>`` tag is where p5 attaches the canvas. Templates placed in ``templates/simple/`` are served at ``/simple/<filename>`` (without the ``.html``), so this one is reachable at ``/simple/my_task``. The page is wrapped in the usual BOFS chrome — header, breadcrumbs, and styling — without any extra effort.

Instructions Page (``task_instructions.html``)
----------------------------------------------

A short instruction page:

.. code-block:: html
    :caption: /p5_example/my_task/templates/instructions/task_instructions.html

    <b>Click</b> as many times as you can before time runs out!

This becomes available at ``/instructions/task_instructions``.

Consent Text (``consent.html``)
-------------------------------

A placeholder consent file. This overwrites the ``consent.html`` produced by ``BOFS init``:

.. code-block:: html
    :caption: /p5_example/consent.html

    Your consent html can go here.

Configuration File (``p5_example.toml``)
----------------------------------------

This file replaces the ``config.toml`` produced by ``BOFS init`` — same role, different name to match the project. Either rename the wizard's file to ``p5_example.toml`` or pass whatever you named it to ``BOFS run``. The ``PAGE_LIST`` ties everything together — consent → instructions → task → end:

.. code-block:: toml
    :caption: /p5_example/p5_example.toml

    # Database settings
    SQLALCHEMY_DATABASE_URI = 'sqlite:///p5_example.db'

    # Must be unique per project. Mash your keyboard or use secrets.token_hex(32).
    SECRET_KEY = 'You Must Change This to Something Unique'

    # Application Settings
    APPLICATION_ROOT = ''
    TITLE = 'P5 Example Project'
    ADMIN_PASSWORD = 'example'
    USE_BREADCRUMBS = true
    PORT = 5002
    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = true
    LOG_QUESTIONNAIRE_INTERACTIONS = false
    CONDITIONS = []

    # External ID page (used here to demonstrate the MTurk wording)
    EXTERNAL_ID_LABEL = "Mechanical Turk Worker ID"
    EXTERNAL_ID_PROMPT = "Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."

    # Completion code shown on the end page
    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = 'Please copy and paste this code into the MTurk form:'

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='Instructions', path='instructions/task_instructions'},
        {name='Task', path='simple/my_task'},
        {name='End', path='end'}
    ]

Running It
----------

From inside the ``p5_example/`` directory:

.. code-block:: bash

    BOFS run p5_example.toml -d

Open http://localhost:5002 to step through the four pages:

.. image:: /examples/p5_example/page0.png
  :alt: Consent page.

.. image:: /examples/p5_example/page1.png
  :alt: Instructions page.

.. image:: /examples/p5_example/page2.png
  :alt: Task page.

.. image:: /examples/p5_example/page3.png
  :alt: End page.
