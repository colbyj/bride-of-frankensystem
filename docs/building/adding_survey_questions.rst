Adding Survey Questions
=======================

Questionnaires in BOFS are JSON files stored in your project's ``questionnaires/`` directory. Each file is one questionnaire and renders as one page in the experiment. For multiple pages of questions, create multiple files.

Questionnaires can also live inside a blueprint at ``<blueprint_name>/questionnaires/``. See :doc:`/framework/blueprints_routes` for how blueprint-scoped questionnaires are discovered.

A minimal example
-----------------

The following file — ``questionnaires/demographics.json`` — collects age and gender:

.. code-block:: json

    {
        "title": "Demographics",
        "instructions": "Please answer the following questions before continuing.",
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
                "labels": ["Man", "Woman", "Non-binary", "Prefer not to say"]
            }
        ]
    }

Every question has three required properties:

- ``id`` — a unique identifier that becomes a column name in the database. Use lowercase letters and underscores (e.g. ``my_question``); avoid SQL reserved words and Python keywords.
- ``questiontype`` — which question type to render (see below).
- ``instructions`` — the question text shown to participants (HTML is accepted).

``required`` is optional and defaults to ``false``.

Common question types
---------------------

**Single-line text** (``field``)

Renders a single text input. Use ``num_field`` for numeric-only input.

.. code-block:: json

    {
        "id": "occupation",
        "questiontype": "field",
        "instructions": "What is your occupation?"
    }

**Single choice from a list** (``radiolist``)

Renders a vertical list of radio buttons. Each entry in ``labels`` is one option.

.. code-block:: json

    {
        "id": "education",
        "questiontype": "radiolist",
        "instructions": "What is the highest level of education you have completed?",
        "labels": [
            "Less than high school",
            "High school diploma or equivalent",
            "Some college",
            "Bachelor's degree",
            "Graduate or professional degree"
        ]
    }

**Rating multiple items on the same scale** (``radiogrid``)

Renders a table where each row is an item and each column is a point on the scale. The ``labels`` list defines the column headers; the ``questions`` list defines the rows.

.. code-block:: json

    {
        "questiontype": "radiogrid",
        "instructions": "How much do you agree with each statement?",
        "labels": [
            "Strongly disagree",
            "Disagree",
            "Neutral",
            "Agree",
            "Strongly agree"
        ],
        "questions": [
            {"id": "enjoy_research", "text": "I enjoy participating in research studies."},
            {"id": "feel_informed", "text": "I feel well informed about this study."},
            {"id": "trust_researcher", "text": "I trust the research team."}
        ],
        "shuffle": true,
        "required": true
    }

``shuffle: true`` randomises the row order each time the page loads. ``required: true`` on a ``radiogrid`` requires every row to have a response before the participant can continue.

The full list of question types — checklists, dropdowns, sliders, multi-line text, and more — with every supported property, is in :doc:`/reference/question_types`.

Adding a questionnaire to PAGE_LIST
------------------------------------

Once the JSON file exists, add it to the ``PAGE_LIST`` in your ``config.toml``. The path format is ``questionnaire/filename`` (without the ``.json`` extension):

.. code-block:: text

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="End", path="end"}
    ]

See :doc:`/building/page_flow` for PAGE_LIST syntax and ordering options.

Required vs optional questions
-------------------------------

Questions are optional by default. Set ``"required": true`` on any question to force a response before the participant can continue:

.. code-block:: json

    {
        "id": "consent_check",
        "questiontype": "radiolist",
        "instructions": "I have read and understood the information above.",
        "labels": ["I agree", "I do not agree"],
        "required": true
    }

Hiding questions based on other answers
-----------------------------------------

A question can include a ``show_if`` property containing an expression. The question is shown only when that expression evaluates to true; otherwise it is hidden.

The following example shows a follow-up only when the participant reports being under 18:

.. code-block:: json

    {
        "questions": [
            {
                "id": "age",
                "questiontype": "num_field",
                "instructions": "What is your age?",
                "required": true
            },
            {
                "id": "parental_consent",
                "questiontype": "radiolist",
                "instructions": "Has a parent or guardian reviewed and consented to your participation?",
                "labels": ["Yes", "No"],
                "show_if": "age < 18"
            }
        ]
    }

The expression ``age < 18`` references the ``id`` of another question in the same questionnaire. The hidden question is also skipped by the ``required`` check — a question that is not visible cannot block submission.

``show_if`` can also reference answers from earlier questionnaires and use boolean operators (``and``, ``or``, ``not``). Full expression syntax is in :doc:`/reference/expressions`.

For hiding entire *pages* based on a participant's answers or condition, see :doc:`/building/conditions_branching`.

Previewing from the admin panel
---------------------------------

Before exposing a questionnaire to participants, preview it from the admin panel:

1. Start your project: ``BOFS run config.toml -d``
2. Visit ``http://localhost:5000/admin`` and log in.
3. Click **Preview Questionnaire** and select the file to view.

The preview renders the questionnaire as participants would see it, reports any JSON syntax errors, and offers to add new database columns if the questionnaire's question IDs have changed since the last run.

.. note::

    **Modifying questionnaires with existing data**

    The database schema for a questionnaire is derived from its question IDs. Changing the questionnaire after responses have been collected requires care.

    *During development*, the simplest approach is to delete the ``.db`` file and restart BOFS — the schema is recreated from scratch on the next run.

    *With live participant data*, you have three options:

    1. Use the admin panel preview. BOFS will offer to add columns for any new question IDs without touching existing data.
    2. Drop the questionnaire's database table. Responses for that questionnaire are lost; everything else stays intact.
    3. Alter the schema manually with SQL. This preserves all data but requires SQL knowledge.

    Renaming or removing an existing question ID breaks the link to any responses already collected. Back up the database before making changes.

.. warning::

    Restart BOFS after editing a questionnaire JSON file — the files are loaded at startup, not on each request.

Further reading
---------------

- :doc:`/reference/question_types` — all question types and their properties.
- :doc:`/reference/questionnaire_properties` — ``{{ }}`` value substitution, ``participant_calculations``, questionnaire naming, and custom question types.
- :doc:`/reference/expressions` — full expression syntax for ``show_if`` and ``{{ }}``.
