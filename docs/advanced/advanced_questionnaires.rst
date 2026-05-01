Advanced Questionnaires
=======================

Participant Calculations and Conditional Display
------------------------------------------------

A questionnaire can compute derived values from a participant's responses (scale scores, reverse-scored items, categorical bins) and can hide individual questions based on the participant's other answers. Both features share a small expression DSL — the same syntax also drives page-level skipping in ``PAGE_LIST``. The full reference for the DSL, the field-reference forms (including qualified ``qname.tag.field`` references for repeated measures), and validation behaviour lives at :doc:`expressions`.

.. code-block:: json
    :caption: A questionnaire that computes a scale score and gates a follow-up question

    {
        "questions": [
            {"id": "ext_1", "questiontype": "slider", "instructions": "I am outgoing",
             "left": "Strongly disagree", "right": "Strongly agree", "tick_count": 7},
            {"id": "ext_2", "questiontype": "slider", "instructions": "I am reserved (reverse scored)",
             "left": "Strongly disagree", "right": "Strongly agree", "tick_count": 7},
            {"id": "ext_3", "questiontype": "slider", "instructions": "I am full of energy",
             "left": "Strongly disagree", "right": "Strongly agree", "tick_count": 7},
            {"id": "elaborate", "questiontype": "field", "show_if": "ext_1 >= 6",
             "instructions": "What activities do you find yourself most outgoing in?"}
        ],
        "participant_calculations": {
            "extraversion": "mean([ext_1, 8 - ext_2, ext_3])"
        }
    }


Creating Custom Question Types
------------------------------

If none of the built-in question types fit, you can define your own by writing an HTML template. BOFS treats any file in ``templates/questions/`` as a custom question type, named after the file.

**Step 1: Create the template**

Create a file in your project's ``templates/questions/`` directory (e.g., ``custom_scale.html``):

.. code-block:: html

    <div class="custom-scale">
        <p>{{ question.instructions }}</p>
        
        <div class="scale-container">
            {% for i in range(1, 8) %}
            <label class="scale-item">
                <input type="radio" name="{{ question.id }}" value="{{ i }}">
                <span class="scale-number">{{ i }}</span>
                {% if i == 1 %}
                    <small>{{ question.low_label }}</small>
                {% elif i == 7 %}
                    <small>{{ question.high_label }}</small>
                {% endif %}
            </label>
            {% endfor %}
        </div>
    </div>
    
    <style>
    .scale-container {
        display: flex;
        justify-content: space-between;
        margin: 20px 0;
    }
    .scale-item {
        text-align: center;
        cursor: pointer;
    }
    </style>

**Step 2: Reference it from a questionnaire**

In a questionnaire JSON, set ``questiontype`` to the template's filename (without the ``.html`` extension):

.. code-block:: json

    {
        "id": "agreement",
        "questiontype": "custom_scale",
        "instructions": "How much do you agree with this statement?",
        "low_label": "Strongly Disagree",
        "high_label": "Strongly Agree"
    }

**Template Variables**

Your custom template has access to:
- ``question``: All properties from your JSON question definition
- ``session``: Flask session data (including participant condition)
- ``participant``: Current participant object with access to previous responses

**Accessing Previous Responses**

You can reference previous questionnaire responses in custom templates:

.. code-block:: html

    <p>Earlier you said your age was: {{ participant.questionnaire("demographics").age }}</p>
    <p>Your assigned condition is: {{ session['condition'] }}</p>

**Multiple IDs**

For questions that need to save multiple values, use the ``questions`` structure:

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

Then loop through them in your template:

.. code-block:: html

    {% for sub_question in question.questions %}
        <input type="text" name="{{ sub_question.id }}" placeholder="{{ sub_question.id|title }}">
    {% endfor %}

Advanced Features
-----------------

**Radiolist with "Other" Option**

Allow participants to specify custom responses:

.. code-block:: json

    {
        "id": "occupation",
        "questiontype": "radiolist",
        "instructions": "What is your occupation?",
        "labels": ["Student", "Teacher", "Engineer", "Other"],
        "other_enabled": true,
        "other_text_prompt": "Please specify:",
        "other_input_width": 200
    }

**Custom Validation**

Add client-side validation to custom question types:

.. code-block:: html

    <script>
    function validateResponse() {
        var selected = $('input[name="{{ question.id }}"]:checked').val();
        if (!selected) {
            alert('Please make a selection');
            return false;
        }
        return true;
    }
    </script>

Database Considerations
-----------------------

Question IDs become column names in the questionnaire's database table and are also used as Python attributes when researchers read responses (e.g. ``participant.questionnaire('demographics').age``). Use lowercase with underscores (``my_question``, not ``MyQuestion``), start with a letter, avoid SQL reserved words (``select``, ``from``, ``where``, etc.), and avoid Python keywords (``class``, ``return``, ``for``, etc.) — a keyword as an attribute name is a syntax error in templates and custom code. The names ``condition`` and ``tables`` are also reserved (they have a special meaning inside expressions; see :doc:`expressions`).

BOFS infers column types from the question type — text fields map to ``TEXT``, number fields to ``INTEGER`` or ``FLOAT``, everything else to ``TEXT`` (JSON-encoded). For changing the schema after participants have submitted data, see "Modifying Questionnaires with Existing Data" in :doc:`../getting_started/basic_questionnaires`.

Next Steps
----------

* For custom database tables, see :doc:`database_tables`.
* For tying questionnaires together with server-side logic, see :doc:`advanced_custom_pages`.