Accessing Participant Data
=========================

This reference guide explains how to access participant data from templates, questionnaires, and custom pages in BOFS. Understanding these patterns is essential for creating dynamic content that adapts based on participant responses and progress.

Template Variables Overview
---------------------------

BOFS automatically provides several variables in templates:

==================== ========================================= ===================================
Variable             Available In                              Description
==================== ========================================= ===================================
``participant``      Instructions, Simple pages, Questions    Current participant object with all data access methods
``session``          All templates                             Flask session with participant ID, condition, etc.
``debug``            All templates                             Boolean indicating if running in debug mode
``config``           All templates                             Access to TOML configuration settings
``flat_page_list``   All templates                             List of all pages in the experiment
==================== ========================================= ===================================

The Participant Object
----------------------

The ``participant`` variable provides access to all participant data through several key methods:

Basic Participant Properties
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: html

    <!-- Core participant information -->
    <p>Participant ID: {{ participant.participantID }}</p>
    <p>Condition: {{ participant.condition }}</p>
    <p>External ID: {{ participant.mTurkID }}</p>
    <p>Started: {{ participant.timeStarted }}</p>
    
    <!-- Status information -->
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

BOFS returns a blank object if a questionnaire hasn't been completed yet:

.. code-block:: html

    {% set survey = participant.questionnaire('follow_up') %}
    
    {% if survey.completed %}
        <p>Follow-up completed: {{ survey.satisfaction }}</p>
    {% else %}
        <p>Follow-up survey not yet completed</p>
    {% endif %}

Accessing Custom Table Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For data stored in custom database tables (defined by JSONTable files), use ``participant.table(name)``:

.. code-block:: html

    <!-- Access custom table data -->
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
    
    <!-- Calculate summary statistics -->
    {% set total_trials = task_data|length %}
    {% set avg_accuracy = (task_data|sum(attribute='accuracy')) / total_trials %}
    <p>Average accuracy: {{ "%.1f"|format(avg_accuracy) }}%</p>

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

.. code-block:: html

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


Best Practices
--------------

**Error Handling**

Always check if data exists before using it:

.. code-block:: html

    {% set survey = participant.questionnaire('optional_survey') %}
    
    {% if survey and survey.completed %}
        <p>Survey rating: {{ survey.rating }}</p>
    {% else %}
        <p>Optional survey not completed</p>
    {% endif %}

**Performance Considerations**

- Cache complex calculations in variables
- Avoid repeated database queries in loops
- Use conditional logic to only process data when needed

**Data Privacy**

- Only display data that participants should see
- Be careful about showing data from other participants
- Consider what information is appropriate to display

**Testing**

- Test templates with participants in different conditions
- Verify data access with both complete and incomplete responses
- Check behavior when questionnaires or tables are empty

Using Data in Custom Blueprint Routes
-------------------------------------

In custom Flask routes, access participant data through the model:

.. code-block:: python

    from flask import session
    from BOFS.default.models import Participant
    
    @blueprint.route('/custom_analysis')
    def custom_analysis():
        participant = Participant.query.get(session['participantID'])
        
        # Access questionnaire data
        demographics = participant.questionnaire('demographics')
        task_data = participant.questionnaire('main_task')
        
        # Access custom table data
        performance = participant.table('task_performance')
        
        # Pass to template
        return render_template('custom_analysis.html',
                             participant=participant,
                             demographics=demographics,
                             task_data=task_data,
                             performance=performance)

This comprehensive data access system allows you to create highly personalized and dynamic experiment experiences that adapt based on participant responses, performance, and progress through your study.