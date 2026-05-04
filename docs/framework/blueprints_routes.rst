Blueprints and Routes
=====================

A blueprint is a folder of Python code that BOFS auto-discovers at startup, registers as a Flask blueprint, and integrates into the experiment flow. Use a blueprint when an experiment page needs server-side logic — generating stimuli on the fly, processing form submissions, writing to a custom table from Python, or talking to an external service.

What "blueprint" means here
---------------------------

In Flask, a `Blueprint <https://flask.palletsprojects.com/en/latest/blueprints/>`_ is a way to group related routes, templates, and static files into a reusable unit. BOFS uses Flask's blueprint system, plus a discovery convention: at startup, BOFS walks your project root looking for folders that contain a ``views.py``. Each one is registered automatically — you don't import or list anything.

The auto-discovery rule is "folder with a ``views.py``." A folder containing only ``__init__.py`` (or only templates) is not picked up.

Blueprint layout
----------------

A blueprint named ``my_blueprint`` lives at the project root:

.. code-block:: text

   my_study/
   ├── config.toml
   ├── consent.html
   └── my_blueprint/
       ├── __init__.py        # marks the folder as a Python package; can be empty
       ├── views.py           # route definitions (required for discovery)
       ├── templates/         # Jinja2 templates, scoped to this blueprint
       ├── static/            # static files, served at /my_blueprint/<path>
       └── tables/            # custom table definitions, scoped to this blueprint

The ``templates/``, ``static/``, and ``tables/`` subdirectories inside a blueprint work the same way as the equivalent directories at the project root. Files inside them are merged into the project's overall template lookup, static-file serving, and table registry — see :doc:`templates_jinja` and :doc:`database_layer` for details.

The views.py boilerplate
------------------------

A minimal ``views.py`` looks like this:

.. code-block:: python

   from flask import Blueprint, render_template, request, redirect, session
   from BOFS.util import verify_correct_page, verify_session_valid
   from BOFS.globals import db

   # The variable name should match the folder name.
   my_blueprint = Blueprint(
       'my_blueprint', __name__,
       static_url_path='/my_blueprint',
       template_folder='templates',
       static_folder='static',
   )

The ``Blueprint()`` constructor arguments rarely need adjusting beyond the name. The rest of the file is your route definitions.

Creating routes
---------------

A route is a Python function decorated with ``@<blueprint>.route``. BOFS adds two of its own decorators on top of Flask's:

.. code-block:: python

   @my_blueprint.route("/task", methods=['POST', 'GET'])
   @verify_correct_page
   @verify_session_valid
   def task():
       if request.method == 'POST':
           log = db.answers()                                # custom table from /tables/answers.json
           log.participantID = session['participantID']
           log.answer = request.form['answer']
           db.session.add(log)
           db.session.commit()

           if log.answer.lower() == "linux":
               return redirect("/redirect_next_page")
           return render_template("task.html", incorrect=True)

       return render_template("task.html")

Three decorators stacked, in order:

- ``@my_blueprint.route("/task", methods=['POST', 'GET'])`` registers the URL and accepts both GETs (loading the page) and POSTs (form submission).
- ``@verify_correct_page`` (from ``BOFS.util``) prevents participants from visiting this page out of order. They must reach it through ``PAGE_LIST``.
- ``@verify_session_valid`` (from ``BOFS.util``) redirects participants to the first page of ``PAGE_LIST`` if their session is missing the expected fields.

Both BOFS decorators are no-ops on routes that aren't reached through ``PAGE_LIST`` — internal admin endpoints, for example. See :doc:`/reference/helper_functions` for the full decorator reference.

GET vs POST
~~~~~~~~~~~

A typical task route handles both: GET renders the page, POST processes the form submission. The pattern in the example above (``if request.method == 'POST': ... return render_template ...``) is standard Flask.

Writing to a custom table
~~~~~~~~~~~~~~~~~~~~~~~~~

Custom tables defined in ``tables/*.json`` are accessible as ORM classes on ``db``. The class name matches the JSON filename (without ``.json``). Create an instance, set attributes, add to the session, and commit — standard SQLAlchemy:

.. code-block:: python

   log = db.answers()
   log.participantID = session['participantID']
   log.answer = request.form['answer']
   db.session.add(log)
   db.session.commit()

The ``participantID`` and ``timeSubmitted`` columns are added to every custom table automatically, but Python code is responsible for populating ``participantID`` (the JS API populates it from the session automatically — Python doesn't). See :doc:`database_layer` for the broader picture and :doc:`/reference/custom_tables` for column types and export keys.

Redirecting participants
~~~~~~~~~~~~~~~~~~~~~~~~

Three built-in routes handle navigation:

- ``/redirect_next_page`` — advance to the next entry in ``PAGE_LIST``.
- ``/redirect_to_page/<path>`` — jump to a specific page.
- ``/redirect_from_page/<path>`` — used internally; rarely called from your code.

Use ``redirect("/redirect_next_page")`` rather than hard-coding the next URL — that way the route works regardless of how the experiment's ``PAGE_LIST`` is reorganized later.

The full route reference is at :doc:`/reference/built_in_routes`.

Templates in blueprints
-----------------------

Templates live in ``my_blueprint/templates/`` and are rendered with ``render_template("filename.html", ...)``. They typically extend BOFS's base template:

.. code-block:: html

   {% extends "template.html" %}

   {% block contents %}
       <h2>Click the button when you're ready.</h2>
       <form method="POST">
           <input type="text" name="answer">
           <button type="submit">Submit</button>
       </form>
       {% if incorrect %}<p>Try again.</p>{% endif %}
   {% endblock %}

Static files inside the blueprint are served at ``/my_blueprint/<path>``. Reference them either with the URL path directly (``/my_blueprint/myscript.js``) or via Flask's ``url_for``:

.. code-block:: html

   <script src="{{ url_for('my_blueprint.static', filename='myscript.js') }}"></script>

Either form works. The ``url_for`` form survives a base-URL change (e.g., when ``APPLICATION_ROOT`` is set for hosting at a subpath); the literal path doesn't.

Template lookup order, override patterns, and the full set of available template variables are covered in :doc:`templates_jinja`.

Showing data on the participant detail page
-------------------------------------------

The admin panel's participant detail view shows each page the participant has visited and (for questionnaire pages) what they submitted. To make a custom-page route surface its data the same way, decorate it with ``@page_tables('<table_name>')``:

.. code-block:: python

   from BOFS.util import page_tables

   @my_blueprint.route("/task", methods=['POST', 'GET'])
   @verify_correct_page
   @verify_session_valid
   @page_tables('answers')
   def task():
       ...

The participant detail page will run the ``answers`` table's calculated export fields scoped to the participant and display the result inline with the page entry. The decorator can list multiple tables. See :doc:`/reference/custom_tables` for export-field syntax and :doc:`/reference/helper_functions` for the decorator reference.

Reading questionnaire data from a route
---------------------------------------

To read the participant's questionnaire responses inside a route, look them up by session ID and use the ``questionnaire()`` method:

.. code-block:: python

   from BOFS.globals import db
   from flask import session

   @my_blueprint.route("/results")
   @verify_correct_page
   @verify_session_valid
   def results():
       participant = db.Participant.query.get(session['participantID'])
       demographics = participant.questionnaire('demographics')

       return render_template(
           "results.html",
           age=demographics.age,
           condition=participant.condition,
       )

For repeated questionnaires (pre/post designs), pass the tag as the second argument: ``participant.questionnaire('mood', 'pre')``. The full participant API is at :doc:`/reference/participant_data_api`. For the broader question of "how do I show participant data in templates?", see :doc:`participant_data`.

Activity polling on custom pages
--------------------------------

Custom pages reached through ``PAGE_LIST`` automatically poll ``/user_active`` every 30 seconds. The poll updates the participant's last-active timestamp, which the admin panel uses to mark a participant as in-progress versus abandoned (after ``ABANDONED_MINUTES`` of silence).

Polling is fine for almost every page, but two cases need to opt out:

- A page that uses ``window.beforeunload`` to capture data before the participant leaves — the poll's network activity can race with the unload handler.
- A long-running task that explicitly manages its own activity heartbeat through a custom table.

Decorate the route with ``@suppress_activity_polling`` to disable the script for that page:

.. code-block:: python

   from BOFS.util import suppress_activity_polling

   @my_blueprint.route("/long_task")
   @verify_correct_page
   @verify_session_valid
   @suppress_activity_polling
   def long_task():
       return render_template("long_task.html")

Implementation note: the decorator sets ``g.bofs_skip_activity_polling = True``, which the response-writing layer reads to skip injecting the polling ``<script>``.

See also
--------

- The `advanced example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/advanced_example>`_ — a worked blueprint with a task page, a custom table, condition-aware routing, and ``@page_tables`` integration.
- The forthcoming custom_blueprint_example — a smaller, single-purpose blueprint walkthrough specifically for this page.
- :doc:`/reference/helper_functions` for the full decorator reference.
- :doc:`/reference/built_in_routes` for the navigation routes.
