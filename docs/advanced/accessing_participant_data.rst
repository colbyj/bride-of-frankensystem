Accessing Participant Data in Templates and Routes
===================================================

When you're writing a custom template (an instruction page, a simple page, a custom question type) or a custom blueprint route, you'll often want to use the participant's existing data — earlier questionnaire responses, rows from a custom table, the assigned condition, the project's configuration. This page covers the variables and methods BOFS exposes for that.

Template Variables
------------------

BOFS provides these variables to every template it renders:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Variable
     - Description
   * - ``participant``
     - Current participant object with data-access methods. ``None`` when no participant is in session (admin previews, the consent page itself, error pages) — guard with ``{% if participant %}`` if your template might render in those cases.
   * - ``session``
     - Flask session: ``session.participantID``, ``session.condition``, ``session.currentUrl``, etc.
   * - ``debug``
     - ``True`` when BOFS is running with ``-d``.
   * - ``config``
     - TOML configuration values.
   * - ``flat_page_list``
     - The participant's filtered page list (after ``show_if`` and condition routing).

The Participant Object
----------------------

Basic Properties
~~~~~~~~~~~~~~~~

.. code-block:: html

    <p>Participant ID: {{ participant.participantID }}</p>
    <p>Condition: {{ participant.condition }}</p>
    <p>External ID: {{ participant.mTurkID }}</p>
    <p>Started: {{ participant.timeStarted }}</p>

    {% if participant.finished %}
        <p>Completed: {{ participant.timeEnded }}</p>
        <p>Duration: {{ participant.display_duration() }}</p>
        <p>Completion Code: {{ participant.code }}</p>
    {% else %}
        <p>Status: {{ participant.display_duration() }}</p>
    {% endif %}

Accessing Questionnaire Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The primary method for accessing questionnaire responses is ``participant.questionnaire(name, tag="")``:

**Basic Usage**

.. code-block:: html

    <!-- Access responses from a questionnaire -->
    {% set demographics = participant.questionnaire('demographics') %}
    
    <h3>Your Information</h3>
    <p>Age: {{ demographics.age }}</p>
    <p>Gender: {{ demographics.gender }}</p>
    <p>Education: {{ demographics.education }}</p>
    
    <!-- Check if a specific response exists -->
    {% if demographics.income %}
        <p>Income range: {{ demographics.income }}</p>
    {% endif %}

**Using Tags for Repeated Questionnaires**

When the same questionnaire is used multiple times in an experiment, use tags to distinguish between them:

.. code-block:: html

    <!-- Pre and post-test mood ratings -->
    {% set pre_mood = participant.questionnaire('mood_scale', 'before') %}
    {% set post_mood = participant.questionnaire('mood_scale', 'after') %}
    
    <h3>Mood Change</h3>
    <p>Before task: {{ pre_mood.mood_rating }}/10</p>
    <p>After task: {{ post_mood.mood_rating }}/10</p>
    <p>Change: {{ post_mood.mood_rating - pre_mood.mood_rating }}</p>

**Accessing Calculated Fields**

Questionnaires can include calculated fields defined in their JSON ``participant_calculations`` section:

.. code-block:: html

    {% set personality = participant.questionnaire('big_five') %}
    
    <!-- These calculated fields are defined in the questionnaire JSON -->
    <h3>Personality Scores</h3>
    <p>Extraversion: {{ personality.extraversion_score }}</p>
    <p>Conscientiousness: {{ personality.conscientiousness_score }}</p>
    <p>Overall Score: {{ personality.total_personality_score }}</p>

**Handling Missing Data**

When a participant hasn't submitted a questionnaire yet, ``participant.questionnaire(name)`` returns a blank-default row — accessing any field gives the column's default value (empty string, ``0``, ``False``). To distinguish a defaulted row from a real submission, use ``participant.has_questionnaire(name, tag='')``:

.. code-block:: html

    {% if participant.has_questionnaire('follow_up') %}
        {% set survey = participant.questionnaire('follow_up') %}
        <p>Follow-up completed: {{ survey.satisfaction }}</p>
    {% else %}
        <p>Follow-up survey not yet completed</p>
    {% endif %}

Accessing Custom Table Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For data stored in custom database tables (see :doc:`database_tables`), ``participant.table(name)`` returns a ``TableAccessor``. Iterate it to walk the participant's raw rows, and read attributes named after the table's ``exports`` block to get per-participant aggregates without writing the SQL yourself.

**Iterating raw rows**

.. code-block:: html

    {% set task_data = participant.table('cognitive_task') %}

    <h3>Task Performance</h3>
    <table>
        <tr><th>Trial</th><th>Response Time</th><th>Accuracy</th></tr>
        {% for trial in task_data %}
            <tr>
                <td>{{ trial.trial_number }}</td>
                <td>{{ trial.response_time }}ms</td>
                <td>{{ trial.accuracy }}%</td>
            </tr>
        {% endfor %}
    </table>

The accessor proxies ``__iter__``, ``len()``, and indexing to ``task_data.rows``, so existing patterns like ``{% for row in task_data %}``, ``task_data|length``, and ``task_data[0]`` continue to work. ``task_data.rows`` is also available explicitly when you want the underlying list.

**Reading per-participant aggregates**

When a JSONTable defines an ``exports`` block, every field declared there is reachable as an attribute on the accessor:

.. code-block:: json

    {
        "columns": {
            "phase": {"default": "learning"},
            "trial_index": {"type": "integer"},
            "correct": {"type": "boolean"}
        },
        "exports": [
            {
                "filter": "phase = 'learning'",
                "fields": {
                    "learning_trials": "count(trial_index)",
                    "learning_accuracy": "avg(correct)"
                }
            }
        ]
    }

.. code-block:: html

    {% set trials = participant.table('cognitive_task') %}

    <p>Learning trials completed: {{ trials.learning_trials }}</p>
    <p>Learning accuracy: {{ "%.0f"|format(trials.learning_accuracy * 100) }}%</p>

Each aggregate runs the export's SQL aggregation restricted to this participant. The result is computed once per accessor instance and cached, so reading ``trials.learning_trials`` twice in the same template only runs the query once. Use ``trials.exports`` to read all scalar aggregates as a dict (``{% for k, v in trials.exports.items() %}``).

If a participant has no rows yet — or no rows that match the export's filter — the aggregate resolves to ``None``. Guard with ``{% if trials.learning_trials is not none %}`` when the absence matters.

Aggregates that use ``group_by`` produce one value per level. The accessor returns these as a dict keyed by the group value:

.. code-block:: html

    {% set trials = participant.table('cognitive_task') %}

    {% for phase, accuracy in trials.phase_accuracy.items() %}
        <p>{{ phase }}: {{ "%.0f"|format(accuracy * 100) }}%</p>
    {% endfor %}

When ``group_by`` is a list of columns, the dict is keyed by a tuple of the column values in declaration order (e.g., ``trials.cell_score[('learning', 1)]``). An empty dict means the participant has no rows that satisfied the export's filter and ``having`` clauses.

Page-level ``show_if`` expressions can only consume scalar aggregates; a ``group_by`` reference like ``tables.cognitive_task.phase_accuracy`` is treated as undecided. Reference the level-suffixed columns in the data export when you need a scalar in a ``show_if`` predicate, or read the dict from the accessor in a template or custom blueprint.

Evaluating an Expression
~~~~~~~~~~~~~~~~~~~~~~~~

When you want the same expression syntax used in ``show_if`` and ``participant_calculations`` from inside a template or a custom route, call ``participant.evaluate(expression)``:

.. code-block:: html

    {% if participant.evaluate("condition == 1 and survey.consent == 'Yes'") %}
        <p>Special instructions for the control condition.</p>
    {% endif %}

    <p>Practice score: {{ participant.evaluate("tables.cognitive_task.learning_accuracy") }}</p>

The expression syntax is documented in :doc:`expressions`. ``participant.evaluate`` returns ``None`` when the expression can't be parsed or when a referenced questionnaire has not been submitted yet, so ``{% if participant.evaluate(...) %}`` is safe to use even on pages that may render before the prior data exists.

For most direct field access, plain Jinja attribute access (``participant.questionnaire('survey').consent``) is shorter and more idiomatic — reach for ``participant.evaluate`` when you want to share an expression string with a config-file ``show_if`` or build the expression dynamically.

Session Variables
-----------------

The Flask ``session`` object provides access to current session data:

.. code-block:: html

    <!-- Session information -->
    <p>Your participant ID: {{ session.participantID }}</p>
    <p>Assigned condition: {{ session.condition }}</p>
    <p>Current page: {{ session.currentUrl }}</p>
    
    {% if session.mTurkID %}
        <p>MTurk Worker ID: {{ session.mTurkID }}</p>
    {% endif %}
    
    {% if session.code %}
        <p>Your completion code: {{ session.code }}</p>
    {% endif %}

Configuration Access
--------------------

Access TOML configuration settings using the ``config`` variable:

.. code-block:: html

    <!-- Study information from config -->
    <h1>{{ config.TITLE }}</h1>
    
    <!-- Use config values in logic -->
    {% if config.REQUIRE_EXTERNAL_ID %}
        <p>External ID is required for this study</p>
    {% endif %}
    
    <!-- Access custom config variables -->
    <p>This study consists of {{ config.TOTAL_ROUNDS }} rounds</p>

Conditional Content by Condition
--------------------------------

Use the participant's condition to show different content:

.. code-block:: html

    <!-- Simple condition check -->
    {% if session.condition == 1 %}
        <p style="color: blue;">You are in the LOW reward condition</p>
    {% elif session.condition == 2 %}
        <p style="color: red;">You are in the HIGH reward condition</p>
    {% else %}
        <p>You are in the control condition</p>
    {% endif %}
    
    <!-- More complex conditional logic -->
    {% set condition_name = ['Control', 'Low Reward', 'High Reward'][session.condition] %}
    <h2>Instructions for {{ condition_name }} Condition</h2>
    
    {% if 'reward' in condition_name.lower() %}
        <div class="reward-info">
            <p>You can earn bonus payments in this condition!</p>
        </div>
    {% endif %}

Advanced Usage Examples
-----------------------

**Displaying Previous Responses for Confirmation**

.. code-block:: html

    <h2>Please Confirm Your Previous Responses</h2>
    
    {% set demo = participant.questionnaire('demographics') %}
    {% set preferences = participant.questionnaire('task_preferences') %}
    
    <div class="confirmation-box">
        <h3>Demographics</h3>
        <ul>
            <li>Age: {{ demo.age }}</li>
            <li>Gender: {{ demo.gender }}</li>
            <li>Education: {{ demo.education }}</li>
        </ul>
        
        <h3>Task Preferences</h3>
        <ul>
            <li>Preferred difficulty: {{ preferences.difficulty }}</li>
            <li>Time limit preference: {{ preferences.time_limit }}</li>
        </ul>
    </div>
    
    <p>Is this information correct?</p>

**Performance Feedback Based on Multiple Sources**

.. code-block:: html+jinja

    {% set task_responses = participant.questionnaire('task_questions') %}
    {% set performance_data = participant.table('task_performance') %}
    
    <h2>Your Performance Summary</h2>
    
    <!-- Calculate overall performance -->
    {% set total_correct = performance_data|sum(attribute='correct') %}
    {% set total_trials = performance_data|length %}
    {% set accuracy = (total_correct / total_trials * 100)|round(1) %}
    
    <div class="performance-summary">
        <p><strong>Overall Accuracy:</strong> {{ accuracy }}%</p>
        <p><strong>Total Trials:</strong> {{ total_trials }}</p>
        <p><strong>Correct Responses:</strong> {{ total_correct }}</p>
        
        <!-- Conditional feedback based on performance -->
        {% if accuracy >= 80 %}
            <p class="feedback-good">Excellent performance!</p>
        {% elif accuracy >= 60 %}
            <p class="feedback-ok">Good job!</p>
        {% else %}
            <p class="feedback-improve">Keep practicing!</p>
        {% endif %}
        
        <!-- Personalized feedback based on questionnaire -->
        {% if task_responses.confidence_rating < 5 %}
            <p>We noticed you rated your confidence as low. Your actual performance shows you did well!</p>
        {% endif %}
    </div>


Using Data in Custom Blueprint Routes
-------------------------------------

In a custom Flask route, look up the participant by ID and use the same ``participant.questionnaire()`` / ``participant.table()`` methods, then pass whatever you need into ``render_template``:

.. code-block:: python

    from flask import session
    from BOFS.default.models import Participant

    @blueprint.route('/custom_analysis')
    def custom_analysis():
        participant = Participant.query.get(session['participantID'])

        demographics = participant.questionnaire('demographics')
        task_data = participant.questionnaire('main_task')
        performance = participant.table('task_performance')

        return render_template('custom_analysis.html',
                             participant=participant,
                             demographics=demographics,
                             task_data=task_data,
                             performance=performance)