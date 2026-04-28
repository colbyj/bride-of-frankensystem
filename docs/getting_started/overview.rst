Overview
========

What is BOFS?
-------------

Bride of Frankensystem (BOFS) is an open-source framework for building and running online behavioral experiments. It sits between general survey tools (which can't host arbitrary tasks) and a fully custom web app (which you'd otherwise build from scratch). BOFS provides the surrounding infrastructure — participant routing, condition assignment, questionnaires, data storage, and an admin panel — so you can focus on the experiment itself.

How BOFS Development Works
--------------------------

A BOFS project moves through three stages:

1. **Develop locally**. Build and run your experiment on your own machine. The project is a folder of configuration and content files that you can edit freely.
2. **Test and debug**. Preview the experiment exactly as participants will see it. The admin panel and debug tools surface any errors before you go live.
3. **Deploy to a server**. Copy the project to a web server when you're ready to recruit participants.

Do I Need Programming Experience?
---------------------------------

For surveys, simple tasks, and A/B testing, no programming is required. You configure your experiment by editing a few plain text files — a settings file that controls the project's behaviour, questionnaire files that describe each set of questions, and HTML files for any custom content (like the consent page or task instructions). The format of each is documented with examples; you'll be copying and adapting more than writing from scratch.

For interactive tasks (clicking on a canvas, dragging things around, watching a video and answering questions about it), some programming experience helps. JavaScript is the usual language for that kind of in-browser task. For tasks that need server-side logic — generating stimuli on the fly, talking to an external service, complex data processing — you'd write Python on top of BOFS. In both cases, BOFS handles the surrounding plumbing (sessions, routing, data storage), so the code you write is just the experiment-specific logic.

BOFS is intended for behavioural researchers who need:

* Custom experiment logic that goes beyond what a survey tool offers
* Integration with external tasks (JavaScript, Unity WebGL, etc.)
* Full ownership of the data, with no licensing fees or vendor lock-in
* Built-in participant tracking, progress monitoring, and data export

How BOFS Compares
-----------------

**vs. Survey Platforms (Qualtrics, SurveyMonkey)**
  * Custom experimental tasks alongside questionnaires, not just questionnaires
  * Open source with no licensing fees or vendor lock-in
  * Direct access to the data and the code that collects it

**vs. JavaScript Libraries for Online Experiments (jsPsych, lab.js)**
  * Backend included — sessions, data storage, condition assignment, admin panel
  * Not an either/or — a jsPsych or lab.js task can run inside a BOFS project, with BOFS providing the consent flow, data storage, and admin panel around it

**vs. Building from Scratch**
  * Participant tracking, condition assignment, and consent flows ready out of the box
  * Documentation and example projects to start from

Where to Go Next
----------------

Start with the :doc:`installation guide <installation>`, then pick a quickstart depending on how you prefer to learn:

* :doc:`Quickstart: Create a New Experiment <quickstart_create>` — generate a fresh project with the ``BOFS init`` wizard and build outward from there.
* :doc:`Quickstart: Run an Existing Experiment <quickstart_existing>` — download the examples repository and walk through a working project end-to-end.

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


Dependencies
------------

BOFS requires Python 3.9+ and the following packages, which are installed automatically alongside BOFS:

* ``flask`` — the web framework BOFS is built on.
* ``sqlalchemy`` — an object-relational mapper used for database table definitions and queries.
* ``flask-sqlalchemy`` — bridge between Flask and SQLAlchemy.
* ``eventlet`` — production web server, used in place of Flask's built-in development server.
* ``toml`` — parser for the TOML configuration files.

