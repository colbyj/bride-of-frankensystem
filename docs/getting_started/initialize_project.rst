Initialize Your First Project
==============================

Step 1: Create a project with ``BOFS init``
--------------------------------------------

BOFS includes an interactive wizard that creates new projects. From your terminal, run:

.. code-block:: bash

   BOFS init

The wizard prompts you for:

1. **Project name** — the directory name (e.g., ``my_experiment``).
2. **Project title** — what participants see in the page header (e.g., ``My First Experiment``).
3. **Admin password** — for logging into ``/admin``.
4. **Features** — toggle with Space, confirm with Enter.

For this walkthrough, select these features:

- ☑ External ID page (MTurk/Prolific)
- ☑ Instructions page
- ☑ Example questionnaires

.. image:: /examples/quickstart/init_wizard.png
   :width: 90%
   :alt: The BOFS init wizard showing feature selection.

When you confirm, the wizard creates the project and offers to start it for you. Choose **Yes** to launch the server and open your browser automatically.

Step 2: What the wizard generated
----------------------------------

.. code-block:: text

   my_experiment/
   ├── config.toml                      # main configuration file
   ├── consent.html                     # consent form content
   ├── questionnaires/
   │   ├── survey.json
   │   ├── demographics.json
   │   └── feedback.json
   └── templates/
       └── instructions/
           └── welcome.html             # instructions page content

**config.toml** holds settings and the page flow:

.. code-block:: toml

   SQLALCHEMY_DATABASE_URI = 'sqlite:///my_experiment.db'
   TITLE = 'My First Experiment'
   ADMIN_PASSWORD = 'admin'
   PORT = 5000

   PAGE_LIST = [
       {name='Consent', path='consent'},
       {name='External ID', path='external_id'},
       {name='Instructions', path='instructions/welcome'},
       {name='Survey', path='questionnaire/survey'},
       {name='End', path='end'},
   ]

``PAGE_LIST`` defines what participants see and in what order. See :doc:`/building/page_flow` to add or rearrange pages, and :doc:`/reference/configuration` for every available setting.

**consent.html** holds the consent text:

.. code-block:: html

   <h1>My First Experiment</h1>
   <h2>Consent to Participate</h2>
   <p>Welcome to this study. Please read the following information carefully.</p>
   <!-- ... fill in purpose, procedures, contact info, IRB number ... -->

Edit this file with your real consent text before running a study with participants. See :doc:`/building/consent` for the full picture, including the four first-page route variants.

**questionnaires/survey.json** is one of three example questionnaires:

.. code-block:: json

   {
       "title": "Survey",
       "instructions": "Please answer the following questions.",
       "questions": [
           {
               "questiontype": "radiogrid",
               "id": "agreement",
               "labels": ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
               "questions": [
                   {"id": "item1", "text": "Statement 1"},
                   {"id": "item2", "text": "Statement 2"}
               ]
           }
       ]
   }

See :doc:`/building/adding_survey_questions` to write your own.

Step 3: Run the project
------------------------

If the wizard didn't start the project for you, start it manually:

.. code-block:: bash

   cd my_experiment
   BOFS run config.toml -d

The ``-d`` flag enables debug mode, which adds a debug toolbar at the bottom of every page and surfaces more detailed error messages. You'll see output like:

.. code-block:: text

   Loading blueprint: BOFS.admin
   Loading blueprint: BOFS.default
   BOFS.default: `models.py` loaded!
   Listening on http://0.0.0.0:5000
   Preview locally at http://127.0.0.1:5000

Open http://localhost:5000 in your browser. To stop the server, press **Ctrl+C** in the terminal.

Step 4: Walk through the experiment
------------------------------------

Each page below is one stop in the participant's journey through the project the wizard generated.

**Consent page.** The first page displays your consent form. Participants click "I Agree" to continue.

.. image:: /examples/quickstart/page_consent.png
   :width: 800
   :alt: The consent page.

**External ID page.** Collects a participant ID, useful when recruiting from MTurk or Prolific. The prompt is configurable via ``EXTERNAL_ID_PROMPT`` in ``config.toml``.

.. image:: /examples/quickstart/page_external_id.png
   :width: 800
   :alt: The external ID page.

**Instructions page.** Renders the HTML in ``templates/instructions/welcome.html``.

.. image:: /examples/quickstart/page_instructions.png
   :width: 800
   :alt: The instructions page.

**Survey page.** Renders questions from the JSON questionnaire. Required questions block submission until they're answered.

.. image:: /examples/quickstart/page_survey.png
   :width: 800
   :alt: The survey page.

**End page.** Shows a generated completion code participants can use to verify participation.

.. image:: /examples/quickstart/page_end.png
   :width: 800
   :alt: The end page.

The admin panel
---------------

Every BOFS project has an admin panel at ``/admin`` (so http://localhost:5000/admin for this project). Log in with the password you set in the wizard.

.. image:: /examples/quickstart/page_admin.png
   :width: 800
   :alt: The admin panel.

The admin panel shows live participant progress, exports the collected data as CSV, previews questionnaires without creating a participant record, and lets you browse the underlying database. Full details: :doc:`/building/monitoring_data`.

Development tips
----------------

- **Replay the experiment.** Use a private/incognito window, or visit ``/restart`` to clear your session and start over.
- **Debug toolbar.** The ``-d`` flag adds a toolbar at the bottom of every page with navigation controls and session information.
- **What restarts.** HTML and JSON changes reflect on the next page load. Editing ``config.toml`` requires restarting the server (Ctrl+C, then ``BOFS run config.toml -d`` again).

Where to go next
----------------

Three forks, depending on what you want to build:

- **Surveys, instruction pages, conditions** — read :doc:`/building/adding_survey_questions`, :doc:`/building/page_flow`, and :doc:`/building/conditions_branching` in order.
- **A JavaScript task** (p5.js, jsPsych, lab.js, Unity) — read :doc:`quickstart_custom_task` next.
- **See what else is possible** — :doc:`quickstart_custom_task` doubles as a tour of BOFS's extensibility.

When you're ready to put the project in front of real participants, see :doc:`/deploying/server`.

Troubleshooting
---------------

- **"Address already in use"** — Another program is using the same port. Edit ``config.toml`` and set a different ``PORT``.
