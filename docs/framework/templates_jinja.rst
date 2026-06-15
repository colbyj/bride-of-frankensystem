Templates and Jinja2
====================

Every page BOFS renders — built-in pages (consent, end, questionnaires) and your own custom ones — goes through `Jinja2 <https://jinja.palletsprojects.com/>`_, the template engine that comes with Flask. This page covers what BOFS does with Jinja2: the lookup order, the base template and its blocks, the variables every template has access to, and the patterns for overriding any of it. Read it when you want to change what participants see beyond content — adding an IRB number or institutional logo to every page, showing condition-specific text, or overriding the consent form layout.

Lookup order
------------

When BOFS renders a template by name (``render_template("foo.html")``), Flask searches three places in this order:

1. **Project ``templates/``** at the project root. This is where your overrides go.
2. **Blueprint ``templates/`` directories**, one per discovered blueprint. Templates here are scoped to that blueprint by default but available to other code via the same lookup.
3. **BOFS's bundled defaults** under ``BOFS/templates/``. The fallback for everything you haven't overridden.

The first match wins. Dropping ``templates/consent.html`` into your project replaces BOFS's default consent template; nothing else changes.

The base template (``template.html``)
-------------------------------------

BOFS ships with a ``template.html`` that defines the page layout — the ``<html>`` shell, the header bar, the content area, the script tags, and (when enabled) the breadcrumb. Every BOFS-rendered page either *is* this template or extends it:

.. code-block:: html

   {% extends "template.html" %}

   {% block contents %}
       <h2>Your content here.</h2>
   {% endblock %}

The blocks defined in the bundled ``template.html`` are:

- ``head`` — additional ``<head>`` content (extra stylesheets, ``<meta>`` tags).
- ``top`` — content rendered above the page title (rare).
- ``contents`` — the main page body (this is the block most pages override).
- ``bottom`` — content rendered below the page body, before the activity-polling script.
- ``scripts`` — additional ``<script>`` tags at the end of ``<body>``.

You don't need to know the bundled template's full source to use it — overriding ``contents`` is enough for almost everything. To customize the page layout itself (header, footer, IRB-required watermark), copy ``template.html`` into your project's ``templates/`` directory and edit your copy.

Available template variables
----------------------------

BOFS injects four variables into every template's context, plus Flask's standard ``session``:

- ``participant`` — the current participant object, or ``None`` outside a session (admin previews, error pages). Guard with ``{% if participant %}`` if your template can render in those contexts.
- ``session`` — the Flask session dict, populated as the participant moves through the experiment.
- ``config`` — the project's TOML config, accessed as ``config['KEY']`` or ``config.KEY``.
- ``debug`` — ``True`` when BOFS is running with ``-d``.
- ``flat_page_list`` — the participant's filtered page sequence, with ``show_if`` and conditional routing already applied.

Each is detailed in :doc:`/reference/participant_data_api`. The most common pattern is reading a questionnaire response or branching on the assigned condition:

.. code-block:: html

   {% if session.condition == 1 %}
       <p>Control instructions go here.</p>
   {% elif session.condition == 2 %}
       <p>Treatment instructions go here.</p>
   {% endif %}

   <p>You answered: {{ participant.questionnaire('demographics').age }}.</p>

For a usage-oriented walkthrough of these variables, see :doc:`participant_data`.

Jinja2 features beyond ``{{ }}`` and ``{% if %}``
-------------------------------------------------

Most templates only need variable substitution and conditionals. Three more Jinja2 features come up regularly:

**Loops** — iterating over a list:

.. code-block:: html

   <ul>
   {% for entry in flat_page_list %}
       <li>{{ entry }}</li>
   {% endfor %}
   </ul>

**Variables in templates** — assigning a name once for reuse:

.. code-block:: html

   {% set demo = participant.questionnaire('demographics') %}
   <p>You are {{ demo.age }} years old.</p>
   <p>You identified as {{ demo.gender }}.</p>

**Filters** — transformations after the ``|``:

.. code-block:: html

   <p>{{ participant.questionnaire('feedback').comments | length }} characters of feedback.</p>
   <p>Started at: {{ participant.timeStarted | string }}</p>

The full filter list is in `Jinja2's documentation <https://jinja.palletsprojects.com/en/stable/templates/#list-of-builtin-filters>`_.

Template override patterns
--------------------------

There are four levels of override, from least to most invasive:

**1. CSS-only changes.** Drop ``static/style.css`` in your project. See :doc:`/building/appearance`.

**2. Override a page template.** Copy a single page template — ``consent.html``, ``end.html``, ``questionnaire.html`` — from BOFS's default into your project's ``templates/`` and edit it. The other pages stay unchanged. The template files BOFS ships are:

.. code-block:: text

   BOFS/templates/
   ├── template.html              # base template (header, layout)
   ├── consent.html               # consent form page
   ├── external_id.html           # external ID collection
   ├── questionnaire.html         # questionnaire page
   ├── questionnaire_macro.html   # rendering helpers used by questionnaire.html
   ├── instructions.html          # instruction page wrapper
   ├── simple.html                # simple-page wrapper
   ├── end.html                   # completion page
   └── questions/                 # one file per built-in question type
       ├── radiolist.html
       ├── radiogrid.html
       ├── slider.html
       └── ...

**3. Override the base template.** Copy ``template.html`` to ``templates/template.html`` and edit it to add a study-branded header, footer, IRB number, or institutional logo. Every page that extends ``template.html`` (which is most of them) inherits the change.

A minimal customized base might look like:

.. code-block:: html
   :caption: templates/template.html

   {% from "macros.html" import adminControls, checkUserActive %}
   <!DOCTYPE html>
   <html>
   <head>
       <title>{{ config['TITLE'] }}</title>
       <link rel="stylesheet" href="{{ url_for('BOFS_static', filename='bootstrap.min.css') }}">
       <link rel="stylesheet" href="{{ style_url }}">
       <script src="{{ url_for('BOFS_static', filename='js/jquery-3.7.1.min.js') }}"></script>
       {% block head %}{% endblock %}
   </head>
   <body>
       <header class="study-header">
           <h2>Psychology Department Research Study</h2>
           <p>IRB Protocol #2026-001</p>
       </header>

       <main class="content">
           {% block top %}{% endblock %}
           {% block contents %}{% endblock %}
           {% block bottom %}{% endblock %}
       </main>

       <footer>
           <p>Questions? Contact research@example.edu</p>
       </footer>

       {{ adminControls() }}
       {{ checkUserActive() }}
   </body>
   </html>

**4. Custom question types.** A ``templates/questions/<type>.html`` file in your project (or in a blueprint) defines a new question type. Set ``"questiontype": "<type>"`` on a question to use it. The full mechanics — what variables the template receives, naming rules, the multiple-IDs pattern for templates that emit several form fields — are documented in :doc:`/reference/questionnaire_properties`.

.. warning::

   Customizations made by overriding bundled templates may stop working when BOFS is upgraded if the upstream templates change. Track the changes you make so you can re-apply them on a fresh copy after upgrading.

Adding custom assets
--------------------

Anything in your project's ``static/`` directory is served at ``/static/<path>``. The same applies to a blueprint's ``static/`` directory, served at ``/<blueprint_name>/<path>``.

For custom fonts, declare ``@font-face`` in ``static/style.css``:

.. code-block:: css

   @font-face {
       font-family: 'UniversityFont';
       src: url('/static/fonts/UniversityFont.woff2') format('woff2');
       font-weight: normal;
   }

   body {
       font-family: 'UniversityFont', 'Segoe UI', Arial, sans-serif;
   }

For images, audio, video, PDFs, downloadable consent forms, JavaScript libraries — drop them in ``static/`` and reference them with their URL path:

.. code-block:: html

   <img src="/static/images/stimulus.png" alt="...">
   <a href="/static/consent.pdf">Download consent form</a>
   <script src="/static/p5.min.js"></script>

See also
--------

- :doc:`/building/appearance` for the no-code styling options (``HEADER_COLOR``, CSS-only overrides).
- :doc:`/reference/participant_data_api` for the full template-variable reference.
- :doc:`participant_data` for usage-oriented examples of reading data in templates.
- :doc:`/reference/questionnaire_properties` for custom question type templates.
