Basic Questionnaires
===================

BOFS includes a powerful questionnaire system for collecting survey data from participants. Questionnaires are defined using JSON files, making them easy to create, modify, and share across projects.

.. note::
    One questionnaire = one page in your experiment. If you need multiple pages of questions, create multiple questionnaire files.

Creating Your First Questionnaire
----------------------------------

Questionnaires are stored as ``.json`` files in your project's ``questionnaires/`` directory. Here's the basic structure:

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

**Complete Questionnaire Structure**

For more complex questionnaires, you can use additional optional properties. For example, if you want to remember the source of a questionnaire, you can include the following properties:

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

======================== ========== ===========================================
Property                 Required   Description
======================== ========== ===========================================
``title``               No         Display name (admin panel only)
``reference``            No         Citation information (admin panel only)
``doi``                  No         DOI link (admin panel only) 
``instructions``         No         Text shown above questions (supports HTML)
``code``                 No         JavaScript code executed at runtime
``questions``            Yes        List of question objects
``participant_calculations`` No     Advanced calculations (see advanced guide)
======================== ========== ===========================================

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

Text Input
^^^^^^^^^^

  For short text responses:

  .. code-block:: json

      {
          "id": "name",
          "questiontype": "field",
          "instructions": "What is your name?"
      }

Number Input
^^^^^^^^^^^^

  For numeric responses:

  .. code-block:: json

      {
          "id": "age",
          "questiontype": "num_field",
          "instructions": "What is your age?",
          "min": 18,
          "max": 99
      }

Multiple Choice (Radio List)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  For single selection from options:

  .. code-block:: json

      {
          "id": "satisfaction",
          "questiontype": "radiolist",
          "instructions": "How satisfied are you?",
          "labels": ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very dissatisfied"]
      }

Checkboxes
^^^^^^^^^^

  For multiple selections:

  .. code-block:: json

      {
          "questiontype": "checklist",
          "instructions": "Select your interests:",
          "questions": [
              {"id": "music", "text": "Music"},
              {"id": "sports", "text": "Sports"},
              {"id": "reading", "text": "Reading"},
              {"id": "travel", "text": "Travel"},
              {"id": "technology", "text": "Technology"}
          ]
      }

**With Text Entry**

You can allow participants to add custom text to specific options:

.. code-block:: json

    {
        "questiontype": "checklist",
        "instructions": "Select your interests:",
        "questions": [
            {"id": "music", "text": "Music"},
            {"id": "other", "text": "Other", "text_entry": true, "text_entry_width": 200}
        ]
    }

Dropdown Menu
^^^^^^^^^^^^^

  For single selection from a long list:

  .. code-block:: json

      {
          "id": "country",
          "questiontype": "drop_down",
          "instructions": "Select your country:",
          "items": ["United States", "Canada", "United Kingdom", "Other"]
      }


Slider Scale
^^^^^^^^^^^^

  For slider scales:

  .. code-block:: json

      {
          "id": "confidence",
          "questiontype": "slider",
          "instructions": "Rate your confidence:",
          "left": "Not confident",
          "right": "Very confident",
          "tick_count": 101
      }


Radio Grids
^^^^^^^^^^^

Radio grids allow participants to rate multiple items using the same scale, displayed in a table format:

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

This creates a table where each row is an item to rate and each column is a rating option.

Additional Radiogrid Options:

- ``shuffle: true`` - Randomize the order of questions
- ``required: true`` - Make all questions in the grid required


.. note::

    For more details about configuring the different types of questions, see :doc:`../questionnaires/question_types`.


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

Before adding questionnaires to your live experiment, preview them in the admin panel:

1. Start your BOFS project: ``BOFS config.toml -d``
2. Visit ``http://localhost:5000/admin`` 
3. Enter your admin password
4. Click "Preview Questionnaire" and select your questionnaire

The preview will:

- Show you how the questionnaire looks to participants
- Check for syntax errors
- Offer to add new database columns if needed

Required vs Optional Questions
-----------------------------

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

If you need to modify a questionnaire after participants have already completed it, you need to be careful about database changes:

**During Development**

- Simply delete your database file (e.g., ``your_study.db``) and restart BOFS
- The database will be recreated with the new structure

**With Live Participant Data**

When you have real participant data, you have several options:

1. **Use Admin Panel Preview** (Recommended)
   - Go to ``/admin`` → "Preview Questionnaire"
   - BOFS will automatically offer to add new columns if needed
   - This is the safest approach for adding new questions

2. **Drop the Questionnaire Table**
   - You lose only the data from that specific questionnaire
   - Other data (demographics, custom tables) remains intact

3. **Manual Database Migration**
   - For complex changes, manually alter the database schema
   - This requires database knowledge but preserves all data

**Important Notes**
- Changing question IDs will break the connection to existing data
- Removing questions may cause errors if the data is referenced elsewhere
- Always backup your database before making changes

.. warning::
    If you change a questionnaires, restart your BOFS application to ensure you've loaded in the updated questionnaires.

Next Steps
----------

- For radio button grids and custom question types, see :doc:`../advanced/advanced_questionnaires`
- For examples of questionnaires in complete experiments, see :doc:`../examples/ab_experiment`
- For all available question types and their options, see :doc:`../questionnaires/question_types`