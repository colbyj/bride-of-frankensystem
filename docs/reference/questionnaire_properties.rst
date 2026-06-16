Questionnaire Properties
========================

A questionnaire is a JSON file in your project's ``questionnaires/`` directory. Each file produces one page of questions and one database table. For a guided introduction to writing questionnaires, see :doc:`/building/adding_survey_questions`.

Top-level properties
--------------------

.. list-table::
   :header-rows: 1
   :widths: 28 10 62

   * - Property
     - Required
     - Description
   * - ``questions``
     - Yes
     - Array of question objects. Must be present; may not be empty.
   * - ``title``
     - No
     - Name shown in the admin panel. Not shown to participants.
   * - ``reference``
     - No
     - Citation text for a validated scale (admin panel only).
   * - ``doi``
     - No
     - DOI string for the instrument (admin panel only).
   * - ``instructions``
     - No
     - Text rendered above the questions. Accepts HTML. Also participates in ``{{ }}`` substitution (see below).
   * - ``code``
     - No
     - A string of JavaScript inserted into the page when it loads in the participant's browser, after the question inputs. Useful for task-specific logic. The value of ``code`` is never HTML-sanitised or ``{{ }}``-substituted — literal ``{{ }}`` in third-party templates is not affected.
   * - ``participant_calculations``
     - No
     - Object mapping calculated column names to expression strings. See `participant_calculations`_ below.
   * - ``database``
     - No
     - Name of a ``SQLALCHEMY_BINDS`` entry from ``config.toml``. Saves this questionnaire's responses to that database instead of the project's main one. See :doc:`/framework/database_layer` for the trade-offs.

BOFS ignores unrecognised top-level keys, so you can add metadata fields for your own reference.


``{{ }}`` substitution
-----------------------

Any user-facing string in a questionnaire can contain ``{{ expression }}`` placeholders. When the questionnaire is rendered for a participant, each placeholder is replaced with the result of evaluating the inner text as an expression (the same syntax used by ``show_if`` and ``participant_calculations`` — see :doc:`/reference/expressions`).

Fields that participate in substitution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Substitution applies to every string-valued field in the JSON that is not on the skip list below, including:

- Top-level: ``title``, ``instructions``
- Per-question: ``title``, ``instructions``, ``left``, ``right``, ``prompt``, ``text``
- List elements: items in ``labels``, ``items``, and the ``text`` field of ``q_text`` entries

Fields that are skipped (values pass through verbatim):

- ``id``, ``questiontype`` — structural identifiers
- ``show_if``, ``participant_calculations``, ``_show_if_ast`` — already use the expression DSL directly
- ``code`` — JS slot; literal ``{{ }}`` is common in third-party templates
- ``src`` — asset URL

Substitution rules
~~~~~~~~~~~~~~~~~~

- Each ``{{ ... }}`` is evaluated once against the current participant's stored data. The substituted value is HTML-escaped, so free-text answers or table values cannot inject markup.
- An expression that returns ``None``, fails to parse, or references data the participant has not yet produced substitutes as an empty string. The surrounding text still renders.
- Substitution is single-pass. A substituted value that itself looks like ``{{ x }}`` is not re-scanned.
- The ``/admin/preview_questionnaire/...`` route renders the raw JSON without substitution so you can inspect the source text.

Because ``{{ }}`` is now reserved inside questionnaire JSON, a questionnaire that previously contained literal ``{{`` in participant-facing copy will render differently. To include a literal ``{{``, write ``{{ '{{' }}``.

Example
~~~~~~~

.. code-block:: json
   :caption: A debrief questionnaire that pulls scores from a JSONTable

   {
       "title": "Your results",
       "instructions": "<p>You scored {{ tables.scores.total_score }} points across all rounds (best: {{ tables.scores.high_score }}).</p>",
       "questions": [
           {
               "id": "thoughts",
               "questiontype": "multi_field",
               "title": "Reflection",
               "instructions": "Round 1: {{ tables.scores.round_score[1] }}. Round 2: {{ tables.scores.round_score[2] }}. What strategy did you use?"
           }
       ]
   }


``participant_calculations``
-----------------------------

The ``participant_calculations`` block computes derived values from a participant's responses. Each key in the object becomes an additional column in the questionnaire's database table and CSV export; the value is an expression string evaluated when data is exported or read back via the participant API.

.. code-block:: json
   :caption: Computing a scale score and a reverse-scored item

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
           "extraversion": "mean([ext_1, 8 - ext_2, ext_3])"
       }
   }

Naming rules for calculated fields:

- Must start with a letter or underscore, followed by letters, digits, or underscores (the same rule as question field IDs).
- Must not be a Python keyword.
- Must not collide with the reserved BOFS columns ``participantID``, ``timeStarted``, ``timeEnded``, ``tag``, or ``duration``.
- Must not collide with the reserved expression names ``condition`` or ``tables``.

For expression syntax, see :doc:`/reference/expressions`.


Question-level ``show_if``
---------------------------

A question can declare a ``show_if`` predicate that controls whether it is visible on the page.

.. code-block:: json

   {
       "questions": [
           {"id": "age", "questiontype": "num_field", "instructions": "How old are you?"},
           {"id": "guardian", "questiontype": "field", "show_if": "age < 18",
            "instructions": "Who is your parent or guardian?"}
       ]
   }

The predicate is evaluated live in the browser as the participant fills out the form. When the predicate is false, the question is hidden and its inputs are excluded from submission — including required fields, which will not block the participant from continuing.

At submission time, a hidden question's database column receives its default value: an empty string for text fields, ``0`` for numeric fields. No submitted value is stored.

BOFS parses every ``show_if`` predicate at startup. A parse error or a reference to an unrecognised field ID is reported immediately with the questionnaire filename and question number.

For expression syntax, see :doc:`/reference/expressions`.


Disabling paste
---------------

Text-entry question types (``field``, ``num_field``, ``multi_field``, and the free-text inputs of ``checklist`` and ``radiolist``) accept a ``disable_paste`` property. When ``true``, paste and drag-drop into that question's input are blocked so the answer has to be typed. To disable paste for every text input in the study at once, set ``DISABLE_PASTE = true`` in your config instead. See :doc:`/reference/question_types` for the per-type property and :doc:`/building/data_quality` for how this fits with interaction logging.


Custom question types
----------------------

If none of the built-in types fit your needs, you can define a custom type by creating a Jinja2 HTML template. BOFS discovers any ``.html`` file in a ``templates/questions/`` directory and registers the filename (without ``.html``) as a valid question type. Template lookup follows the same precedence order as all BOFS templates; see :doc:`/framework/templates_jinja` for details.

Creating a custom type
~~~~~~~~~~~~~~~~~~~~~~

Place a file at ``templates/questions/<your_type>.html`` in your project directory (or in a blueprint). In a questionnaire JSON, set ``"questiontype"`` to the filename without the extension:

.. code-block:: json

   {
       "id": "agreement",
       "questiontype": "custom_scale",
       "instructions": "How much do you agree with this statement?",
       "low_label": "Strongly Disagree",
       "high_label": "Strongly Agree"
   }

Template variables
~~~~~~~~~~~~~~~~~~

Every custom question template receives these variables:

- ``question`` — the full question dict from the JSON, including any custom properties you added (``low_label``, ``high_label``, etc.).
- ``participant`` — the current :class:`Participant` model instance. Provides access to previously submitted questionnaire responses via ``participant.questionnaire('name').field``.
- ``session`` — the Flask session dict. Injected by Flask into every Jinja context. Contains ``condition`` (the participant's assigned condition number) and other session keys set by BOFS or your own blueprints.

The template must produce one or more ``<input>`` elements whose ``name`` attributes match the question's ``id`` (or, for multi-value types, the sub-question IDs) so that the form submission is captured and stored correctly.

Example template:

.. code-block:: html

   <div class="custom-scale">
       <p>{{ question.instructions }}</p>
       <div class="scale-container">
           {% for i in range(1, 8) %}
           <label>
               <input type="radio" name="{{ question.id }}" value="{{ i }}">
               {{ i }}
               {% if i == 1 %}<small>{{ question.low_label }}</small>{% endif %}
               {% if i == 7 %}<small>{{ question.high_label }}</small>{% endif %}
           </label>
           {% endfor %}
       </div>
   </div>

The multiple-IDs pattern
~~~~~~~~~~~~~~~~~~~~~~~~

A custom type can save multiple values per question by using a nested ``questions`` list. Each entry in that list needs its own ``id``; those IDs become the database column names.

.. code-block:: json

   {
       "questiontype": "contact_form",
       "instructions": "Contact Information",
       "questions": [
           {"id": "first_name"},
           {"id": "last_name"},
           {"id": "phone"}
       ]
   }

In the template, iterate over ``question.questions``:

.. code-block:: html

   {% for sub in question.questions %}
       <input type="text" name="{{ sub.id }}" placeholder="{{ sub.id }}">
   {% endfor %}

Some built-in types also use this pattern (``radiogrid``, ``checklist``). The ``EXPANDED_TYPES`` mechanism in ``BOFS/validation.py`` covers the special case of a single top-level ``id`` that expands to multiple suffixed columns — ``video`` and ``audio`` work this way, writing ``<id>_started``, ``<id>_ended``, and ``<id>_watched`` / ``<id>_listened`` to the database.


Question ID naming rules
-------------------------

Question IDs become column names in the questionnaire's database table — and therefore the column headers in your exported CSV — and are read back as Python attributes (e.g. ``participant.questionnaire('demographics').age``). The following rules apply to both question field IDs and ``participant_calculations`` keys:

- Must match the pattern ``[A-Za-z_][A-Za-z0-9_]*`` — a letter or underscore, then any mix of letters, digits, and underscores.
- Must not be a Python keyword (``class``, ``return``, ``for``, etc.). Keywords are syntax errors when used as attribute names in templates and custom code.
- Must not be one of the reserved BOFS column names: ``participantID``, ``participant``, ``tag``, ``timeStarted``, ``timeEnded``, ``duration``.
- Must not be one of the reserved expression names: ``condition``, ``tables``. These have special meaning inside ``show_if`` and ``participant_calculations`` expressions.
- Must be unique within a questionnaire. Duplicate IDs in the same file are a validation error.

Column type inference
~~~~~~~~~~~~~~~~~~~~~

BOFS infers the SQLAlchemy column type from the question type:

.. list-table::
   :header-rows: 1
   :widths: 35 25 40

   * - Question type
     - Column type
     - Notes
   * - ``slider``, ``num_field``, ``checklist``
     - ``INTEGER``
     -
   * - ``image_select``
     - ``INTEGER`` or ``FLOAT``
     - Inferred from the ``value`` fields in the ``images`` list; falls back to ``TEXT`` when values are mixed or non-numeric.
   * - Everything else
     - ``TEXT``
     -

To override the inferred type, add ``"datatype"`` to the question definition with one of: ``"integer"``, ``"float"``, ``"string"``, ``"datetime"``, or ``"boolean"``.


Modifying questionnaires with existing data
--------------------------------------------

The database schema for a questionnaire is derived from its question IDs. Changing the schema after participants have submitted responses needs care.

**During development**, delete the database file (e.g. ``your_study.db``) and restart BOFS. The schema is recreated from scratch on the next run.

**With live participant data**, three paths are available:

1. **Admin panel preview** — visit ``/admin`` and use "Preview Questionnaire". BOFS will offer to add columns for new question IDs without touching existing data.
2. **Drop the questionnaire table** — deletes responses for that questionnaire while leaving other tables (demographics, custom data) intact.
3. **Manual schema migration** — alter the database directly using SQL. This preserves all data but requires knowledge of the underlying schema.

Changing or removing an existing question ID breaks the link to previously collected responses. Back up the database before making schema changes.

Questionnaire JSON files are loaded at startup. Restart BOFS after editing a questionnaire file.

Orphaned columns (columns that exist in the database but are no longer defined in the JSON) are preserved with ``NULL`` for new submissions and flagged as validation warnings at startup.
