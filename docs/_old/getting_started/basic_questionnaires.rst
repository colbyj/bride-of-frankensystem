Basic Questionnaires
====================

Questionnaires in BOFS are defined as JSON files in your project's ``questionnaires/`` directory. Each file is one questionnaire and renders as one page; for multiple pages of questions, create multiple files.

Creating Your First Questionnaire
----------------------------------

A minimal questionnaire looks like this:

.. code-block:: json

    {
        "title": "My First Questionnaire",
        "instructions": "Please answer the following questions:",
        "questions": [
            {
                "id": "age",
                "questiontype": "num_field",
                "instructions": "What is your age?",
                "required": true
            },
            {
                "id": "gender",
                "questiontype": "radiolist",
                "instructions": "What is your gender?",
                "labels": ["Male", "Female", "Non-binary", "Prefer not to say"]
            }
        ]
    }

**Full set of top-level properties**

A questionnaire can also include citation metadata, runtime JavaScript, and per-participant calculations:

.. code-block:: json

    {
        "title": "Questionnaire Name",
        "reference": "Smith, J. (2023). My Scale. Journal of Psychology.",
        "doi": "10.1000/journal.2023.001",
        "instructions": "Instructions shown to participants (supports HTML)",
        "code": "// Optional JavaScript code executed at runtime",
        "questions": [ /* your questions here */ ],
        "participant_calculations": { /* advanced calculations */ }
    }

Key Components
--------------

**Questionnaire Properties**

============================ ========== ===========================================
Property                     Required   Description
============================ ========== ===========================================
``title``                    No         Display name (admin panel only)
``reference``                No         Citation information (admin panel only)
``doi``                      No         DOI link (admin panel only)
``instructions``             No         Text shown above questions (supports HTML)
``code``                     No         JavaScript code executed at runtime
``questions``                Yes        List of question objects
``participant_calculations`` No         Advanced calculations (see advanced guide)
============================ ========== ===========================================

.. note::
    You can add custom properties to questionnaires for your own reference - BOFS will ignore any unrecognized keys.

**Question Properties**

=================== ========== ===========================================
Property            Required   Description
=================== ========== ===========================================
``id``              Yes        Unique identifier (becomes database column)
``instructions``    Yes        Question text shown to participants
``questiontype``    Yes        Question type (see types below)
``required``         No         Whether answer is required (default: false)
=================== ========== ===========================================

Common Question Types
---------------------

A few representative examples follow. The full set of question types — checklists, dropdowns, sliders, multi-line text, and so on — along with every supported property, lives in :doc:`../reference/question_types`.

**Single-line text** (``field``)

.. code-block:: json

    {
        "id": "name",
        "questiontype": "field",
        "instructions": "What is your name?"
    }

**Single-choice from a list of labels** (``radiolist``)

.. code-block:: json

    {
        "id": "satisfaction",
        "questiontype": "radiolist",
        "instructions": "How satisfied are you?",
        "labels": ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very dissatisfied"]
    }

**Rating multiple items on the same scale** (``radiogrid``)

Renders as a table where each row is an item to rate and each column is a point on the scale.

.. code-block:: json

    {
        "questiontype": "radiogrid",
        "instructions": "Rate your satisfaction with each aspect:",
        "labels": [
            "Very dissatisfied",
            "Dissatisfied",
            "Neutral",
            "Satisfied",
            "Very satisfied"
        ],
        "questions": [
            {"id": "sat_food", "text": "Food quality"},
            {"id": "sat_service", "text": "Service quality"},
            {"id": "sat_atmosphere", "text": "Atmosphere"}
        ]
    }

Add ``"shuffle": true`` to randomize the row order, or ``"required": true`` to require an answer for every row.


Adding Questionnaires to Your Experiment
----------------------------------------

Once you've created a questionnaire file (e.g., ``demographics.json``), add it to your experiment by including it in the ``PAGE_LIST`` in your configuration file:

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='Demographics', path='questionnaire/demographics'},
        {name='End', path='end'}
    ]

The path format is always ``questionnaire/filename`` (without the ``.json`` extension).

Previewing Questionnaires
-------------------------

Preview a questionnaire from the admin panel before exposing it to participants:

1. Start your BOFS project: ``BOFS run config.toml -d``
2. Visit ``http://localhost:5000/admin`` and enter your admin password.
3. Click "Preview Questionnaire" and select the questionnaire to view.

The preview renders the questionnaire as participants would see it, surfaces any JSON syntax errors, and offers to add new database columns if the questionnaire structure has changed since the last run.

Required vs Optional Questions
------------------------------

By default, all questions are optional. To make a question required:

.. code-block:: json

    {
        "id": "consent_check",
        "questiontype": "radiolist",
        "instructions": "I consent to participate in this study",
        "labels": ["Yes", "No"],
        "required": true
    }

Required questions must be answered before participants can continue.

Modifying Questionnaires with Existing Data
-------------------------------------------

The database schema for a questionnaire is derived from its question IDs. Changing the questionnaire after participants have submitted responses needs care.

**During development**, the simplest approach is to delete the database file (e.g., ``your_study.db``) and restart BOFS — the schema is recreated from scratch on the next run.

**With live participant data**, you have three options:

1. **Admin panel preview**. Visit ``/admin`` → "Preview Questionnaire". BOFS will offer to add columns for any new question IDs without touching existing data.
2. **Drop the questionnaire's table**. You lose responses for that one questionnaire; everything else (demographics, custom tables) stays intact.
3. **Manual schema migration**. For more involved changes, alter the database schema by hand. This preserves all data but requires SQL knowledge.

Either way: changing or removing existing question IDs breaks the link to any responses already collected, and you should back up the database before making changes.

.. warning::
    Restart BOFS after changing a questionnaire — the JSON files are loaded at startup.

Next Steps
----------

- For embedding custom calculations into questionnaires and creating custom question types, see :doc:`../advanced/advanced_questionnaires`.
- For complete example projects, see :doc:`../examples/example_projects`.
- For all available question types and their options, see :doc:`../reference/question_types`.