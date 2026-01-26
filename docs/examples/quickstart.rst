Quickstart Guide
================

This guide will walk you through creating your first BOFS project. By the end, you'll have a working
experiment with a consent form, participant ID collection, instructions, and a survey.

Prerequisites
-------------

Make sure BOFS is installed before continuing. If you haven't installed it yet, follow the
:doc:`/getting_started/installation` guide first.

Creating Your Project
---------------------

BOFS includes an interactive wizard that creates new projects. Open your terminal and run:

.. code-block:: bash

    BOFS init

The wizard will guide you through the setup process:

1. **Project name**: Enter a name for your project directory (e.g., ``my_experiment``)
2. **Project title**: Enter the title participants will see (e.g., ``My First Experiment``)
3. **Admin password**: Set a password for the admin panel (default is ``admin``)
4. **Features**: Select the features to include using Space to toggle and Enter to confirm

For this quickstart, select the following features:

- ☑ External ID page (MTurk/Prolific)
- ☑ Instructions page
- ☑ Example questionnaires

.. image:: /examples/quickstart/init_wizard.png
   :width: 600
   :alt: The BOFS init wizard showing feature selection.

After confirming, the wizard will create your project and ask if you want to start it immediately.
Choose **Yes** to launch the server and open your browser automatically.

Project Structure
-----------------

The wizard creates the following files:

.. code-block:: text

    my_experiment/
    ├── config.toml                      # Main configuration file
    ├── consent.html                     # Consent form content
    ├── questionnaires/
    │   ├── survey.json                  # Main survey questionnaire
    │   ├── demographics.json            # Demographics questionnaire
    │   └── feedback.json                # Feedback questionnaire
    └── templates/
        └── instructions/
            └── welcome.html             # Instructions page content

Let's examine the key files.

config.toml
~~~~~~~~~~~

This is the main configuration file that controls your experiment:

.. code-block:: toml

    # Database settings
    SQLALCHEMY_DATABASE_URI = 'sqlite:///my_experiment.db'

    # Security - change this to something unique in production
    SECRET_KEY = 'your-generated-secret-key'

    # Application Settings
    TITLE = 'My First Experiment'
    ADMIN_PASSWORD = 'admin'
    USE_BREADCRUMBS = true
    PORT = 5000

    # External ID Settings
    EXTERNAL_ID_LABEL = "Participant ID"
    EXTERNAL_ID_PROMPT = "Please enter your participant ID from the recruitment platform."

    # Page List - defines the experiment flow
    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='External ID', path='external_id'},
        {name='Instructions', path='instructions/welcome'},
        {name='Survey', path='questionnaire/survey'},
        {name='End', path='end'},
    ]

Key configuration options:

- ``SQLALCHEMY_DATABASE_URI``: Where participant data is stored (SQLite by default)
- ``SECRET_KEY``: Secures session cookies (auto-generated, keep it secret in production)
- ``TITLE``: Displayed in the browser tab and page headers
- ``ADMIN_PASSWORD``: Password for the ``/admin`` panel
- ``PAGE_LIST``: Defines the sequence of pages participants see

For a complete list of options, see :doc:`/reference/config_options`.

consent.html
~~~~~~~~~~~~

This file contains the HTML content for your consent form:

.. code-block:: html

    <h1>My First Experiment</h1>

    <h2>Consent to Participate</h2>

    <p>Welcome to this study. Please read the following information carefully.</p>

    <div>
        <h3>Purpose</h3>
        <p>[Describe the purpose of your study here]</p>

        <h3>Procedures</h3>
        <p>[Describe what participants will be asked to do]</p>
        <!-- ... -->
    </div>

Edit this file to include your actual consent information before running a real study.

survey.json
~~~~~~~~~~~

Questionnaires are defined in JSON format. Here's the structure of the generated survey:

.. code-block:: json

    {
        "title": "Survey",
        "instructions": "Please answer the following questions.",
        "questions": [
            {
                "questiontype": "radiogrid",
                "instructions": "Rate your agreement with the following statements.",
                "id": "agreement",
                "labels": ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
                "questions": [
                    {"id": "item1", "text": "Statement 1"},
                    {"id": "item2", "text": "Statement 2"},
                    {"id": "item3", "text": "Statement 3"}
                ]
            }
        ]
    }

To learn more about questionnaire options and question types, see :doc:`/getting_started/basic_questionnaires`.

Running Your Project
--------------------

If you didn't start the project from the wizard, you can start it manually:

.. code-block:: bash

    cd my_experiment
    BOFS run config.toml -d

The ``-d`` flag enables debug mode, which provides helpful error messages during development.

You should see output similar to:

.. code-block:: text

    Loading blueprint: BOFS.admin
    Loading blueprint: BOFS.default
    BOFS.default: `models.py` loaded!
    survey
    Listening on http://0.0.0.0:5000
    Preview locally at http://127.0.0.1:5000

Open http://localhost:5000 in your browser to view your experiment.

Stopping the Server
~~~~~~~~~~~~~~~~~~~

To stop BOFS, press **Ctrl+C** in the terminal where it's running. You'll see a message confirming
the server has shut down.

Walking Through the Experiment
------------------------------

Let's go through each page a participant would see.

Consent Page
~~~~~~~~~~~~

.. image:: /examples/quickstart/page_consent.png
   :width: 800
   :alt: The consent page.

The first page displays your consent form. Participants must click "I Agree" to continue.

External ID Page
~~~~~~~~~~~~~~~~

.. image:: /examples/quickstart/page_external_id.png
   :width: 800
   :alt: The external ID page.

This page collects a participant ID, useful when recruiting from platforms like MTurk or Prolific.
The prompt text is configurable via ``EXTERNAL_ID_PROMPT`` in your config file.

Instructions Page
~~~~~~~~~~~~~~~~~

.. image:: /examples/quickstart/page_instructions.png
   :width: 800
   :alt: The instructions page.

The instructions page displays content from ``templates/instructions/welcome.html``.
Edit this file to provide study-specific instructions to your participants.

Survey Page
~~~~~~~~~~~

.. image:: /examples/quickstart/page_survey.png
   :width: 800
   :alt: The survey page.

The survey page renders questions from your JSON questionnaire file. Participants must complete
all required questions before continuing.

End Page
~~~~~~~~

.. image:: /examples/quickstart/page_end.png
   :width: 800
   :alt: The end page.

The final page shows a completion code that participants can use to verify their participation.
This is automatically generated and can be configured in your config file.

The Admin Panel
---------------

Every BOFS project includes an admin panel at ``/admin``. Navigate to http://localhost:5000/admin
and enter your admin password.

.. image:: /examples/quickstart/page_admin.png
   :width: 800
   :alt: The admin panel.

The admin panel provides:

- **Progress**: Real-time view of participant progress through the study
- **Export**: Download collected data as CSV files
- **Preview Questionnaires**: Test questionnaires without creating participant records
- **Database Tables**: Browse the raw database contents

For detailed documentation of admin features, see :doc:`/getting_started/admin`.

Next Steps
----------

Now that you have a working project, here are some ways to extend it:

**Customize your questionnaires**
    Edit the JSON files in ``questionnaires/`` or create new ones. See :doc:`/getting_started/basic_questionnaires` for all available question types.

**Add custom pages**
    Create HTML templates for tasks or additional content. See :doc:`/getting_started/simple_custom_pages`.

**Set up experimental conditions**
    Randomly assign participants to different groups. See the conditions section in :doc:`/getting_started/project_configuration`.

**Add custom logic with Python**
    Create Flask blueprints for advanced functionality. See :doc:`/advanced/advanced_custom_pages`.

**Store custom data**
    Define your own database tables for task data. See :doc:`/advanced/database_tables`.

**Deploy for participants**
    When ready to collect real data, see :doc:`/deployment/server_config`.

Tips for Development
--------------------

.. TIP::
    Use a private/incognito browser window when testing, or visit ``/restart`` to clear your
    session and start over from the beginning.

.. TIP::
    The ``-d`` flag enables debug mode with a toolbar at the bottom of each page showing
    navigation controls and session information.

.. TIP::
    Changes to HTML templates and JSON questionnaires are reflected immediately. For config
    changes, restart the server (Ctrl+C, then run again).
