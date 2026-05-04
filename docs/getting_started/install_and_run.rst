Install and Run Your First Project
==================================

The short version
-----------------

If you already know your way around Python:

1. **Install Python 3.9+.**
2. **Install the framework:** ``pip install bride-of-frankensystem``
3. **Create your project:** ``BOFS init``
4. **Run it:** ``BOFS run config.toml -d``

That's the whole flow. The rest of this page walks through each step in detail — recommended virtual-environment setup, what the ``BOFS init`` wizard generates, what the participant sees on each page, and where to go next.

BOFS runs on Windows, Mac, and Linux.

Step 1: Install Python
----------------------

BOFS requires Python 3.9 or newer. Check what's already installed:

- **Windows**: Open Command Prompt (search "cmd") and run ``python --version``.
- **Mac/Linux**: Open Terminal and run ``python3 --version``.

If you see ``Python 3.9.x`` or higher, continue. Otherwise, download Python from https://python.org.

Step 2: Install BOFS
--------------------

Install BOFS into an isolated environment so its dependencies don't conflict with other Python projects on your machine. Pick whichever toolchain you're more comfortable with — both arrive at the same result.

.. note::
   If you only ever plan to work on a single BOFS project, you can skip the isolated environment and install BOFS into your system Python with ``pip install bride-of-frankensystem``. Working on multiple projects this way can cause dependency conflicts down the line.

.. tabs::

   .. tab:: pip + venv

      The standard approach using Python's built-in tools.

      **2.1 Open your command line.**

      - **Windows**: Command Prompt or PowerShell
      - **Mac**: Terminal (via Spotlight)
      - **Linux**: your terminal application

      **2.2 Create the virtual environment.**

      .. code-block:: bash

         python -m venv bofs_venv

      This creates a ``bofs_venv`` folder containing its own copy of Python. Anything you install while the environment is active goes here instead of into your system Python, so different projects can use different package versions without conflicting.

      **2.3 Activate it.**

      - **Windows (Command Prompt)**: ``.\bofs_venv\Scripts\activate.bat``
      - **Windows (PowerShell)**: ``.\bofs_venv\Scripts\Activate.ps1``
      - **Mac/Linux**: ``source bofs_venv/bin/activate``

      Your prompt should now be prefixed with ``(bofs_venv)``. Subsequent ``python`` and ``pip`` commands will use the virtual environment. Activate it again each time you open a new terminal.

      **2.4 Install BOFS.**

      .. code-block:: bash

         pip install bride-of-frankensystem

      ``pip`` is Python's package installer. This downloads BOFS and its dependencies from the Python Package Index. It may take a minute or two.

      **2.5 Test the installation.** Run ``BOFS``. You should see a help message listing the available commands.

   .. tab:: uv

      `uv <https://docs.astral.sh/uv/>`_ is a Python package manager from Astral. Its ``uv tool`` command installs Python applications into isolated environments and adds them to your PATH, so you don't need to activate anything before running BOFS.

      **2.1 Install uv.** Follow the `uv installation instructions <https://docs.astral.sh/uv/getting-started/installation/>`_ for your operating system.

      **2.2 Install BOFS as a tool.**

      .. code-block:: bash

         uv tool install bride-of-frankensystem

      This creates a dedicated environment for BOFS behind the scenes and makes the ``BOFS`` command available globally. Open a new terminal afterwards so the updated PATH takes effect.

      **2.3 Test the installation.** Run ``BOFS``. You should see a help message listing the available commands.

Step 3: Get a text editor
-------------------------

You'll be editing config files and HTML templates. Any text editor works; these have syntax highlighting and project navigation that make the job easier:

- **Visual Studio Code** (free): https://code.visualstudio.com
- **Sublime Text**: https://www.sublimetext.com
- **PyCharm** (full IDE, with Python tooling built in): https://www.jetbrains.com/pycharm/

Step 4: Create a project with ``BOFS init``
-------------------------------------------

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
   :width: 600
   :alt: The BOFS init wizard showing feature selection.

When you confirm, the wizard creates the project and offers to start it for you. Choose **Yes** to launch the server and open your browser automatically.

Step 5: What the wizard generated
---------------------------------

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

Step 6: Run the project
-----------------------

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

Step 7: Walk through the experiment
-----------------------------------

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

- **"python not found"** — Make sure Python is installed and added to your system PATH.
- **"pip not found"** — On Windows, allow the installer to add Python to your PATH. On Linux, ``pip`` may be a separate package.
- **"BOFS not found"** — If you used pip + venv, make sure the virtual environment is activated. As a fallback, ``python -m BOFS run config.toml`` is equivalent to ``BOFS run config.toml``.
- **"Permission denied"** — Try your command line as administrator (Windows) or with ``sudo`` (Mac/Linux).
- **"Address already in use"** — Another program is using the same port. Edit ``config.toml`` and set a different ``PORT``.
