Advanced Questionnaires
======================

This section covers advanced questionnaire features including calculations, custom question types, and complex layouts.

Participant Calculations
------------------------

You can perform calculations with questionnaire responses on a per-participant basis. This is useful for computing scores, scales, or derived metrics.

Calculations are defined in the ``participant_calculations`` section of your questionnaire:

.. code-block:: json

    {
        "title": "Personality Scale",
        "questions": [
            {
                "id": "extraversion_1",
                "questiontype": "slider",
                "instructions": "I am outgoing, sociable",
                "left": "Strongly disagree",
                "right": "Strongly agree",
                "tick_count": 7
            },
            {
                "id": "extraversion_2", 
                "questiontype": "slider",
                "instructions": "I am reserved (reverse scored)",
                "left": "Strongly disagree",
                "right": "Strongly agree",
                "tick_count": 7
            },
            {
                "id": "extraversion_3",
                "questiontype": "slider",
                "instructions": "I am full of energy",
                "left": "Strongly disagree",
                "right": "Strongly agree",
                "tick_count": 7
            }
        ],
        "participant_calculations": {
            "extraversion_score": "mean([extraversion_1, 8-extraversion_2, extraversion_3])",
            "extraversion_category": "'High' if extraversion_score > 5 else 'Low'"
        }
    }

**Available Functions**

- ``mean(list)``: Calculate average
- ``variance(list)``: Calculate variance  
- ``std(list)``: Calculate standard deviation
- ``median(list)``: Calculate median

**Python Expressions**

Calculations can use any valid Python expression, including:

- Arithmetic operations: ``+``, ``-``, ``*``, ``/``
- Conditional expressions: ``value if condition else other_value``
- Comparisons: ``>``, ``<``, ``==``, ``!=``
- Boolean logic: ``and``, ``or``, ``not``

.. warning::
    Calculations run in an unsandboxed Python environment. Only use trusted questionnaire files.


Creating Custom Question Types
-----------------------------

For maximum flexibility, you can create entirely custom question types using HTML templates.

**Step 1: Create Template File**

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

**Step 2: Use in Questionnaire**

Reference your custom question type in your questionnaire JSON:

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
----------------

**Conditional Display**

Use JavaScript in the ``code`` field to show/hide questions based on responses:

.. code-block:: json

    {
        "code": "
            $('#age').on('input', function() {
                if ($(this).val() < 18) {
                    $('#parental_consent').show();
                } else {
                    $('#parental_consent').hide();
                }
            });
        "
    }

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
----------------------

**Column Names**

Question IDs become database column names. Follow these guidelines:
- Use lowercase with underscores (``my_question`` not ``MyQuestion``)
- Start with a letter, not a number
- Avoid SQL reserved words (``select``, ``from``, ``where``, etc.)

**Data Types**

BOFS automatically infers column types:

- Text fields → TEXT
- Number fields → INTEGER or FLOAT
- All others → TEXT (JSON stored as string)

**Schema Changes**

When you modify questionnaires with existing data:
1. Use the admin panel preview to add new columns automatically
2. For complex changes, manually alter the database schema
3. For development, delete the database file and restart

Next Steps
----------

- For database table customization, see :doc:`database_tables`
- For integrating questionnaires with custom logic, see :doc:`advanced_custom_pages`
- For complete examples, see :doc:`../examples/ab_experiment`