What is BOFS?
=============

Bride of Frankensystem (BOFS) is an open-source framework for building online behavioral experiments and surveys. Instead of a drag-and-drop editor, you describe your study in plain-text files — a configuration file for settings and page flow, JSON files for questionnaires, and HTML files for custom pages. BOFS handles participant routing, condition assignment, consent forms, data storage, and provides an admin panel for monitoring and export.

Where BOFS fits
---------------

If you have used other tools for online studies, BOFS sits at a specific spot in the landscape.

- **Survey platforms (Qualtrics, SurveyMonkey, Google Forms)** handle questionnaires with point-and-click editing on hosted infrastructure. They cannot embed a JavaScript task or open the data layer for custom logic. If your study is questionnaires only and your institution already provides Qualtrics, that may be a simpler choice.
- **JavaScript experiment libraries (jsPsych, lab.js, PsychoJS)** handle in-browser trial logic — precise timing, key capture, randomization. They do not host the surrounding study (consent, condition assignment, sessions, admin panel). A jsPsych, lab.js, or PsychoJS task can run inside a BOFS custom page; the two are complementary.
- **Custom Flask, Django, or Express applications** give you full control of every detail, and full responsibility for everything else. When BOFS's built-in patterns are not enough, it exposes the same Flask underneath — custom routes drop into the same project.

BOFS sits in the middle: research-specific scaffolding (consent, conditions, sessions, data storage, admin panel) plus an open boundary for questionnaires, JavaScript tasks, or Python where each is the right fit.

How BOFS development works
--------------------------

A BOFS project moves through three stages:

1. **Develop locally.** Build and run the experiment on your own machine. The project is a folder of configuration and content files you can edit freely.
2. **Test and debug.** Preview the experiment exactly as a participant will see it. The admin panel and debug tools surface errors before you go live.
3. **Deploy to a server.** Copy the project to a web server when you are ready to recruit participants. See :doc:`/deploying/server`.


A simple project
----------------

A BOFS project is a collection of files, each controlling one aspect of the experiment. The simplest BOFS project is a folder with three pieces:

.. image:: /getting_started/images/simple_project.svg
   :width: 80 %
   :align: center
   :alt: Simple project file structure — config.toml, consent.html, and questionnaires/

The pieces
~~~~~~~~~~

This file structure is all that is needed for questionnaire-based projects. It allows you to do the following:

.. tab-set::

    .. tab-item:: Show a consent form

        .. image:: /getting_started/images/simple_project_consent.svg
            :width: 80 %
            :alt: Annotated consent.html content

        The consent form is an HTML file at the project root. BOFS wraps it in a form with "I consent" and "I do not consent" buttons, records the response, and creates the participant entry in the database.

        See :doc:`/building/consent` for the consent flow, route variants, multi-stage consent, and IRB notes.

    .. tab-item:: Ask questions

        .. image:: /getting_started/images/simple_project_questions.svg
           :width: 80 %
           :alt: Annotated questionnaire JSON content

        Questionnaires are JSON files — one file per page of questions. BOFS renders the form, validates required fields, and stores the responses automatically.

        See :doc:`/building/adding_survey_questions` for question types, conditional visibility, and more.

    .. tab-item:: Control the page order

        .. image:: /getting_started/images/simple_project_config.svg
           :width: 80 %
           :alt: Annotated config.toml content

        ``PAGE_LIST`` in ``config.toml`` defines the sequence of pages a participant moves through, along with settings like the study title, port, and database. Add, remove, or reorder pages by editing the list.

        See :doc:`/building/page_flow` for required settings, page types, and running the same questionnaire multiple times.


Even with these three files, BOFS already covers common research needs:

- **Random assignment.** Define groups in your config; BOFS assigns each participant and keeps the groups balanced as they enroll.
- **Item-order randomization.** Set "shuffle" on a rating grid or radio list to present items in a random order for each participant, controlling for position effects without any code.
- **Conditional questions.** Hide a question — or a whole page — when an earlier answer makes it irrelevant. Participants only see what applies to them.
- **Reusing earlier answers.** Embed a previous response into a later question's wording — for instance, show participants the rating they just gave and ask them to explain it.
- **Computed scores.** Sum a Likert block, reverse-score specific items, or define any calculation over a page's responses; BOFS evaluates it as the participant submits.
- **Repeated measurements.** Present the same questionnaire more than once — for pre/post within a single session. Or, have participants come back days or weeks later, and load their condition assignment or progress through the study based on an external ID.
- **Live monitoring.** The admin panel shows where each participant currently is, in real time.
- **Descriptive statistics on demand.** The admin panel shows N, mean, standard deviation, and median for every numeric question — broken down by condition — along with box plots, useful for inspecting pilot data without exporting to a stats package.

The page types
--------------

Every BOFS experiment is a sequence of pages defined in ``PAGE_LIST`` (inside ``config.toml``). A typical experiment starts with consent, moves through your pages, and ends:

.. image:: /getting_started/images/page_list_paths.svg
   :width: 100 %
   :alt: PAGE_LIST page types — built-in pages, scaffolded pages, and blueprint-defined pages

The diagram above shows all available page types, organized into three tiers:

.. grid:: 3
    :gutter: 2

    .. grid-item-card::  Built-in Pages

        Require no files — just add them to ``PAGE_LIST``. BOFS handles consent forms, participant creation, external ID collection, and experiment completion.

        No code or markup required.

    .. grid-item-card::  Scaffolded Pages

        Require an additional file to add. For questionnaires, a JSON file. For instruction, simple, or custom pages, an HTML file. BOFS automatically provides navigation, automatic validation and data storage, depending on the type of page.

        Some basic markup is required. To make full use of simple or custom pages, you can use HTML and JavaScript.

    .. grid-item-card::  Blueprint-Defined Pages

        Require an additional directory and specific files to add to your project. For when the built-in and scaffolded options are not enough. You write Python routes (Flask) and BOFS auto-discovers them.

        Knowledge of Python, HTML, and JavaScript is an asset.


More pieces
-----------

The simple project's three files cover questionnaire-based studies. To go past that, you add directories to the same folder — nothing about the simple project has to change.

.. image:: /getting_started/images/advanced_project.svg
   :width: 80 %
   :align: center
   :alt: Advanced project file structure — tables, templates, static, and blueprint directories

.. tab-set::

    .. tab-item:: Add your own pages

        .. code-block:: html

           <h2>Welcome</h2>
           <p>In this study you will read short scenarios and answer
              a few questions about each one.</p>
           <p>Click <strong>Continue</strong> when you are ready.</p>

        HTML files in ``templates/instructions/``, ``templates/simple/``,
        or ``templates/custom/`` become pages in your study. Instruction
        pages get an automatic Continue button; simple pages give you
        full control over navigation; custom pages drop the BOFS chrome
        entirely so you can host an embedded JavaScript task.

        See :doc:`/building/your_own_pages` for the differences between
        the three and how to wire navigation.

    .. tab-item:: Serve static files

        .. code-block:: text

           static/
           ├── stimulus_a.png
           ├── stimulus_b.png
           ├── instructions.pdf
           └── p5.min.js

        Files in ``static/`` are served at ``/static/<path>``. Use it
        for images, audio, video, downloadable PDFs, and any JavaScript
        libraries your custom pages depend on.

        See :doc:`/building/your_own_pages` for embedding static assets
        in instruction, simple, and custom pages.

    .. tab-item:: Store custom data

        .. code-block:: json

           {
               "columns": {
                   "score": "integer",
                   "reaction_time": "float",
                   "stimulus": "string"
               }
           }

        Custom tables are JSON-defined database tables for the data
        your study generates beyond questionnaire responses — task
        scores, trial-by-trial events, mouse movement. JavaScript on a
        page POSTs to ``/table/<name>``; BOFS handles storage and
        exposes the rows in the admin panel.

        See :doc:`/building/storing_custom_data` for column types,
        the JS read/write API, and calculated export fields.

    .. tab-item:: Add Python routes

        .. code-block:: python

           from flask import Blueprint, render_template
           from BOFS.util import verify_correct_page

           my_blueprint = Blueprint('my_blueprint', __name__,
                                    template_folder='templates')

           @my_blueprint.route('/task')
           @verify_correct_page
           def task():
               return render_template('my_blueprint/task.html')

        A blueprint is a folder at your project root containing
        ``views.py`` (and optionally its own ``templates/``, ``static/``,
        or ``tables/``). BOFS auto-discovers it and loads the routes
        you define — for when you need server-side logic, custom
        database queries, or anything else beyond what scaffolded pages
        can do.

        See :doc:`/framework/blueprints_routes` for blueprint layout,
        route decorators, and writing to custom tables from Python.

Where to go next
----------------

Read :doc:`installation` next to install BOFS, then :doc:`initialize_project` to generate a project with the ``BOFS init`` wizard and run it.

.. toctree::
   :hidden:

   self
   installation
   initialize_project
   quickstart_custom_task
