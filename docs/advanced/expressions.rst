Expressions: Calculations and Conditional Display
==================================================

Three places in BOFS take a small expression written over a participant's responses: the ``participant_calculations`` block on a questionnaire and per-question ``show_if`` predicates (both described in :doc:`advanced_questionnaires`), and per-page ``show_if`` predicates inside ``PAGE_LIST`` (described in :doc:`/getting_started/project_configuration`). They all accept the same syntax, so this page is the canonical reference for the syntax itself.

Where expressions are used
--------------------------

============================================ ========================= =====================================
Where you write it                            When it runs              A field name on its own refers to
============================================ ========================= =====================================
``participant_calculations`` (questionnaire)  When data is exported     A field on the same questionnaire row
Question-level ``show_if`` (questionnaire)    Live, in the browser      Another field on the same page
Page-level ``show_if`` (``PAGE_LIST``)        At each page navigation   A field on any prior questionnaire
============================================ ========================= =====================================

Each expression is checked once when BOFS launches. A typo or an unsupported piece of syntax raises an error at startup, not silently at the moment a participant lands on the page.

Syntax
------

Expressions look like Python expressions, restricted to a small safe subset. Whether your expression runs on the server (calculations, page skipping) or in the browser (live question hiding), the result is the same — the syntax and the rules are identical.

You can use:

* Arithmetic: ``+``, ``-``, ``*``, ``/``, integer division ``//``, remainder ``%``
* Comparisons: ``<``, ``<=``, ``>``, ``>=``, ``==``, ``!=`` (and the chained form, e.g. ``0 < x < 10``)
* Logic: ``and``, ``or``, ``not``
* Membership: ``in``, ``not in`` (against a list, e.g. ``country in ['US', 'CA']``, or a string)
* If/else as a value: ``a if condition else b``

Values you can write directly:

* Numbers (``42``, ``3.14``)
* Strings, with single or double quotes (``'High'``, ``"Other"``)
* ``True``, ``False``, ``None``
* Lists: ``[1, 2, 3]``, or lists of expressions like ``[q1, 8 - q2, q3]``

Functions you can call:

* Aggregates: ``mean``, ``median``, ``stdev``, ``std``, ``var``, ``variance``
* Common: ``len``, ``min``, ``max``, ``sum``, ``abs``, ``round``
* Type conversion: ``int``, ``float``, ``str``, ``bool``

What you cannot use: arbitrary function calls (only the names above are permitted), method calls on values (``x.lower()``), indexing into a list with brackets (``items[0]``), and Python-only constructs such as ``lambda`` or list comprehensions. If a participant's questionnaire response needs reshaping in those ways, do it in your analysis script after export rather than inside an expression.

Referring to participant data
-----------------------------

A field name on its own — ``age``, ``q1``, ``01_inv`` (field IDs that start with a digit work too) — refers to a stored value. What it actually resolves to depends on where you wrote it:

* Inside ``participant_calculations``, it is a field from the same questionnaire's row (the one whose calculation is being computed).
* Inside a question-level ``show_if``, it is another field on the same page, read live from the browser as the participant types or clicks.
* Inside a page-level ``show_if``, it is looked up across every questionnaire the participant has already submitted; the most recent matching submission wins.

Page-level ``show_if`` also accepts more specific reference forms when the same questionnaire appears in ``PAGE_LIST`` multiple times under different tags (for example, a wellbeing questionnaire filled in once before an intervention and once after):

================================ ===================================================
Form                              Resolves to
================================ ===================================================
``qname.field``                   Most recent submission of ``qname`` (any tag)
``qname.tag.field``               The row of ``qname`` submitted under the given tag
``qname..field``                  The row of ``qname`` with the empty (default) tag
================================ ===================================================

The ``tag`` segment matches the second part of paths like ``questionnaire/qname/tag``. The qualified forms only apply to page-level ``show_if`` — the other two surfaces always look at a single questionnaire row, so there is nothing to disambiguate.

Calculations on a questionnaire
-------------------------------

A ``participant_calculations`` block computes derived values from a participant's responses — scale scores, reverse-scored items, categorical bins. The result is stored alongside the raw responses and shows up as its own column in the CSV export. The block lives inside a questionnaire's JSON file (see :doc:`advanced_questionnaires`).

.. code-block:: json

    {
        "questions": [
            {"id": "ext_1", "questiontype": "slider", "instructions": "I am outgoing",
             "left": "Strongly disagree", "right": "Strongly agree", "tick_count": 7},
            {"id": "ext_2", "questiontype": "slider", "instructions": "I am reserved (reverse scored)",
             "left": "Strongly disagree", "right": "Strongly agree", "tick_count": 7},
            {"id": "ext_3", "questiontype": "slider", "instructions": "I am full of energy",
             "left": "Strongly disagree", "right": "Strongly agree", "tick_count": 7}
        ],
        "participant_calculations": {
            "extraversion": "mean([ext_1, 8 - ext_2, ext_3])",
            "high_extraversion": "mean([ext_1, 8 - ext_2, ext_3]) > 5"
        }
    }

Each key under ``participant_calculations`` becomes an export column with the computed value. The keys must follow the same naming rules as field IDs (start with a letter or underscore, alphanumerics and underscores after) and must not collide with the built-in BOFS columns ``participantID``, ``timeStarted``, ``timeEnded``, ``tag``, or ``duration``.

Hiding a question
-----------------

A question inside a questionnaire (see :doc:`advanced_questionnaires`) can declare a ``show_if`` predicate that branches on the participant's other answers on the same page. The expression is checked live in the browser as the participant fills out the page; when it is false, the question is hidden and the form treats its inputs as if they weren't there — including any required fields, which won't block submission.

.. code-block:: json

    {
        "questions": [
            {"id": "age", "questiontype": "num_field", "instructions": "How old are you?"},
            {"id": "guardian", "questiontype": "field", "show_if": "age < 18",
             "instructions": "Who is your parent or guardian?"},
            {"id": "lang", "questiontype": "drop_down",
             "items": ["English", "French", "Spanish", "Other"],
             "instructions": "Primary language"},
            {"id": "lang_other", "questiontype": "field", "show_if": "lang == 'Other'",
             "instructions": "Please specify"}
        ]
    }

When a question is hidden at submission time, no value is sent and the database column receives its default — an empty string for text fields, ``0`` for numeric fields, and so on.

Skipping a page
---------------

Any entry in ``PAGE_LIST`` (including entries inside a ``conditional_routing`` block) can carry a ``show_if`` predicate that branches on the participant's stored answers. When the predicate is false, the page is removed from that participant's flow — the next/back navigation skips past it and it does not appear in their breadcrumb. ``PAGE_LIST`` itself lives in your project's configuration file (see :doc:`/getting_started/project_configuration`).

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Followup", path="questionnaire/followup", show_if="demographics.age < 18"},
        {name="End", path="end"}
    ]

For repeated-measures designs that fill in the same questionnaire more than once under different tags, the qualified reference forms compare specific submissions:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Pre-survey", path="questionnaire/wellbeing/before"},
        {name="Intervention", path="task/intervention"},
        {name="Post-survey", path="questionnaire/wellbeing/after"},
        {name="Improvement debrief", path="debrief/improved", show_if="wellbeing.before.score < wellbeing.after.score"},
        {name="End", path="end"}
    ]

When a page-level ``show_if`` references a questionnaire the participant has not yet submitted, the page stays visible — the predicate is treated as undecided rather than removing a page on the basis of data that hasn't been collected.

Errors and validation
---------------------

* A bad expression — unsupported syntax or a disallowed function — raises an error when BOFS starts up, naming the calculation or the question or the page that contains it.
* A reference to a field ID that doesn't exist on the relevant questionnaire is reported as a validation warning at startup, listing the questionnaire's known field IDs alongside the unknown one to help you catch typos.
