Bride of Frankensystem
======================

`Bride of Frankensystem <https://frankensystem.net>`_ (BOFS) is an open-source framework for online behavioral experiments and surveys. It sits between survey-only platforms (Qualtrics, SurveyMonkey) and building from scratch: editing TOML, JSON, and HTML gets you a running study, and Python is available when you need it.

A survey-only project
---------------------

The simplest BOFS project is a folder with three pieces:

.. code-block:: text

   my_study/
   ├── config.toml          # settings, page sequence, conditions
   ├── consent.html         # the consent form participants see
   └── questionnaires/      # one JSON file per survey page
       └── demographics.json

That's a working study. ``config.toml`` lists the pages a participant moves through, ``consent.html`` is the form they sign on arrival, and the JSON files in ``questionnaires/`` define the questions. Run the project with ``BOFS run config.toml`` and the admin panel at ``/admin`` shows progress and exports the data.

Going further
-------------

To go past surveys, you add pieces to the same project folder. Nothing about the survey-only base case has to change:

- **Static instruction pages.** HTML files in ``templates/instructions/``.
- **Conditions and branching.** A ``CONDITIONS`` block in ``config.toml`` with conditional routing, or per-page ``show_if`` predicates over questionnaire answers.
- **Embedded JavaScript tasks** (p5.js, jsPsych, lab.js, Unity). HTML in ``templates/custom/`` plus a custom data table (JSON in ``tables/``). The task POSTs to a built-in route; BOFS handles the storage.
- **Server-side logic.** A Python blueprint at the project root — a folder with a ``views.py`` defining routes. BOFS auto-discovers it.

Each addition is documented in *Building Your Experiment*. The framework concepts behind them (Flask, SQLAlchemy, Jinja2) are documented in *Understanding the Framework*, only when you need them.

Where to start
--------------

- Never used BOFS? — :doc:`getting_started/what_is_bofs` then :doc:`getting_started/install_and_run`.
- Already installed? — :doc:`getting_started/install_and_run` walks through ``BOFS init`` and what it generates.
- Want a JavaScript task? — :doc:`getting_started/quickstart_custom_task`.

.. note::

   If you need additional help, please `join us on Discord <https://discord.gg/XzXtUKFCJA>`_.


.. toctree::
   :maxdepth: 1
   :caption: Getting Started

   getting_started/what_is_bofs
   getting_started/install_and_run
   getting_started/quickstart_custom_task

.. toctree::
   :maxdepth: 1
   :caption: Building Your Experiment

   building/adding_survey_questions
   building/page_flow
   building/consent
   building/your_own_pages
   building/conditions_branching
   building/longitudinal
   building/storing_custom_data
   building/monitoring_data
   building/appearance

.. toctree::
   :maxdepth: 1
   :caption: Understanding the Framework

   framework/architecture
   framework/blueprints_routes
   framework/templates_jinja
   framework/participant_data
   framework/database_layer
   framework/sessions

.. toctree::
   :maxdepth: 1
   :caption: Deploying Your Experiment

   deploying/server
   deploying/recruiting

.. toctree::
   :maxdepth: 1
   :caption: Reference

   reference/configuration
   reference/question_types
   reference/questionnaire_properties
   reference/expressions
   reference/custom_tables
   reference/participant_data_api
   reference/built_in_routes
   reference/cli
   reference/helper_functions


Citation
--------

If you use BOFS for your research, please cite it:

.. code-block:: bibtex

    @software{bride-of-frankensystem,
      author       = {Colby Johanson},
      title        = {colbyj/bride-of-frankensystem},
      month        = may,
      year         = 2024,
      publisher    = {Zenodo},
      version      = {2.0},
      doi          = {10.5281/zenodo.11176739},
      url          = {https://doi.org/10.5281/zenodo.11176739}
    }
