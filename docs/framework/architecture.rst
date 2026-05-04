The BOFS Architecture
=====================

This section is for developers who want to go past the built-in patterns — write Python routes, render dynamic templates, query the database directly, or understand how sessions work. If you're configuring an experiment with TOML, JSON, and HTML and don't need any of that, you can stop at the :doc:`/index` toctree's "Building Your Experiment" section.

What BOFS actually is
---------------------

Under the hood, BOFS is a Python web application built on `Flask <https://flask.palletsprojects.com/>`_, with an extended ``BOFSFlask`` class on top that adds three things:

- **TOML configuration loading**, so settings live in human-friendly ``.toml`` files instead of Python.
- **Blueprint auto-discovery**, so a folder containing a ``views.py`` at your project root is registered automatically without an explicit Python import.
- **Database-backed sessions**, replacing Flask's default file-based session interface so participants don't lose state when a worker process restarts.

If you've used Flask before, that's the whole story: a Flask app with conventions baked in. If you haven't, you don't need to learn Flask first — most projects never touch it directly. But if you do start writing Python, what you're writing *is* Flask, and the same Flask documentation applies.

The request lifecycle
---------------------

When a participant visits a URL, here's the order of operations:

1. **Session lookup.** BOFS's database-backed session middleware (``BOFSSession.py``) reads the session cookie and loads the corresponding row. New visitors get a fresh session.
2. **Routing.** Flask matches the URL against the registered routes — those defined in BOFS's built-in default blueprint (``BOFS.default``), the admin blueprint (``BOFS.admin``), and any project-level blueprints discovered at startup.
3. **Page-flow validation.** Routes that participate in ``PAGE_LIST`` use the ``@verify_correct_page`` decorator to confirm the URL matches the participant's current position. A mismatch redirects them back to where they should be.
4. **View execution.** The route function runs. It may read questionnaire data from the participant record, query custom tables, render a template, or process a form submission.
5. **Template rendering.** Templates extend ``BOFS/templates/template.html`` and inherit a context that already includes ``participant``, ``session``, ``config``, ``debug``, and ``flat_page_list``.
6. **Storage.** Form submissions write to a participant-specific row in the questionnaire's auto-generated table; ``$.post`` calls to ``/table/<name>`` write to a custom table.

The participant then gets a response, advances, and the loop repeats.

Where BOFS's code ends and yours begins
---------------------------------------

BOFS exposes a small number of well-defined extension points. Each has its own page later in this section.

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Extension point
     - What you write
     - Where it lives
   * - Questionnaires
     - JSON files
     - ``questionnaires/*.json`` at the project root, or ``<blueprint>/questionnaires/*.json``
   * - Custom tables
     - JSON files
     - ``tables/*.json`` at the project root, or ``<blueprint>/tables/*.json``
   * - Static pages
     - HTML files
     - ``templates/instructions/``, ``templates/simple/``, ``templates/custom/``
   * - Custom routes
     - Python (Flask blueprint)
     - A folder with ``__init__.py`` and ``views.py`` at the project root
   * - Template overrides
     - HTML/Jinja2
     - ``templates/`` files matching BOFS's default template names
   * - Visual styling
     - CSS
     - ``static/style.css``

A project that uses only the first three rows is a "no Python" project. Adding the fourth opens up server-side logic. Templates and CSS overrides apply at any level.

The project folder as a configuration surface
---------------------------------------------

A BOFS project is a folder. The contents of that folder, plus any Python blueprints inside it, define the entire experiment. Nothing about the experiment is configured in BOFS itself. This is what makes a BOFS project portable — copying the folder copies the experiment.

A representative project at the framework level looks like:

.. code-block:: text

   my_study/
   ├── config.toml                  # settings, PAGE_LIST, conditions
   ├── consent.html                 # consent form
   ├── questionnaires/
   │   └── *.json                   # one per survey page
   ├── templates/
   │   ├── instructions/*.html      # static instruction pages
   │   ├── simple/*.html            # custom pages with BOFS chrome
   │   ├── custom/*.html            # custom pages without BOFS chrome
   │   ├── questions/*.html         # custom question type templates (optional)
   │   └── template.html            # base template override (optional)
   ├── tables/
   │   └── *.json                   # custom database tables
   ├── static/
   │   ├── style.css                # CSS overrides (optional)
   │   ├── *.js                     # JavaScript task files
   │   └── images, audio, video, etc.
   └── my_blueprint/                # custom Python blueprint (optional)
       ├── __init__.py
       ├── views.py
       ├── templates/               # blueprint-scoped templates
       ├── static/                  # blueprint-scoped static files
       └── tables/                  # blueprint-scoped custom tables

Each subdirectory is auto-discovered by BOFS at startup. You don't import anything from BOFS in your blueprint's ``__init__.py``; you just declare a Flask ``Blueprint`` object and write routes in ``views.py``. BOFS finds it.

How the pieces connect
----------------------

A complete request flow, end-to-end:

1. ``config.toml`` declares ``PAGE_LIST`` — the ordered sequence of pages.
2. The participant arrives, consent is recorded (or skipped, depending on the first-page route), and a row is created in the ``Participant`` table.
3. The ``@verify_correct_page`` decorator routes them through the pages declared in ``PAGE_LIST`` in order. Each page is one of: a built-in route (``consent``, ``external_id``, ``end``), a questionnaire, a static HTML page (``instructions/``, ``simple/``, ``custom/``), or a custom blueprint route.
4. Form submissions populate per-questionnaire database tables (auto-generated from the JSON definitions). JavaScript tasks POST to ``/table/<name>`` and populate custom tables (auto-generated from your ``tables/*.json`` definitions).
5. The ``/admin`` panel reads from these same tables to display progress, preview questionnaires, and export data.

The rest of this section walks each layer in turn:

- :doc:`blueprints_routes` — Flask blueprints in BOFS terms, ``views.py``, route decorators.
- :doc:`templates_jinja` — template inheritance, Jinja2 features, all available variables, override patterns.
- :doc:`participant_data` — the ``participant`` object, accessing questionnaire and table data, expressions in templates.
- :doc:`database_layer` — SQLAlchemy in BOFS, built-in models, custom table internals, querying, export field mechanics.
- :doc:`sessions` — database-backed sessions, session lifecycle, recovery, IP binding.

See also: the `advanced example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/advanced_example>`_ in the example projects repo — a worked project that touches most of these extension points in one place.
