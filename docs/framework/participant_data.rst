Using Participant Data
======================

This page covers how to read participant data — questionnaire responses, custom-table rows, condition assignment, session state — from inside templates and Python routes. The exhaustive method-level reference is at :doc:`/reference/participant_data_api`; here we focus on the patterns you'll actually reach for.

The participant object
----------------------

The current participant is available as the ``participant`` variable in every BOFS-rendered template, and as ``db.Participant.query.get(session['participantID'])`` in custom blueprint routes.

The participant object has a small set of database-backed attributes (``participantID``, ``condition``, ``externalID``, ``timeStarted``, ``finished``, ``code``) and a few methods that return their related data. ``externalID`` is also accessible as ``mTurkID`` — both names refer to the same column, with ``mTurkID`` kept as an alias for backward compatibility.

- ``participant.questionnaire(name, tag="")`` — the response row, with each field accessible as an attribute.
- ``participant.has_questionnaire(name, tag="")`` — boolean; was the questionnaire submitted at all.
- ``participant.questionnaire_interactions(name, tag="")`` — the interaction event log (when ``LOG_QUESTIONNAIRE_INTERACTIONS = true``).
- ``participant.table(name)`` — a ``TableAccessor`` for a custom JSONTable; iterates rows, reads export aggregates.
- ``participant.evaluate(expression)`` — runs an expression DSL (the same one used by ``show_if``) against the participant's data.

Reading questionnaire responses
-------------------------------

The ``questionnaire()`` method returns a row whose fields are accessible as attributes. The field names are the question IDs from the questionnaire JSON:

.. code-block:: html

   {% set demo = participant.questionnaire('demographics') %}
   <p>Age: {{ demo.age }}, Education: {{ demo.education }}.</p>

If the participant hasn't submitted that questionnaire yet, the call still returns a row — one with default values (empty strings, zeros). To distinguish between "not yet submitted" and "submitted but empty," use ``has_questionnaire()``:

.. code-block:: html

   {% if participant.has_questionnaire('feedback') %}
       Feedback received: {{ participant.questionnaire('feedback').comments }}
   {% else %}
       Feedback not yet collected.
   {% endif %}

Tagged (repeated) questionnaires
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For pre/post designs and longitudinal studies, the same questionnaire is submitted multiple times under different tags (see :doc:`/building/page_flow` for tagging in PAGE_LIST). Pass the tag as the second argument:

.. code-block:: html

   {% set pre  = participant.questionnaire('mood', 'pre') %}
   {% set post = participant.questionnaire('mood', 'post') %}
   <p>Mood improved from {{ pre.score }} to {{ post.score }}.</p>

Reading custom-table data
-------------------------

``participant.table(name)`` returns a ``TableAccessor`` that handles three things:

1. **Iterate the raw rows** the participant submitted to that table.
2. **Read the calculated export fields** declared in the table's ``exports`` block.
3. **Compute scoped aggregates** — every export is automatically scoped to this participant.

.. code-block:: html

   {% set trials = participant.table('trial_data') %}

   {# Iterate raw rows #}
   <ul>
   {% for row in trials %}
       <li>Trial {{ loop.index }}: {{ row.score }}</li>
   {% endfor %}
   </ul>

   {# Read scalar export aggregates #}
   <p>Total trials: {{ trials.trial_count }}</p>
   <p>Average RT: {{ trials.avg_rt | round(1) }} ms</p>

For exports declared with ``group_by``, the accessor returns a dict keyed by the group value:

.. code-block:: html

   {% set scores = participant.table('game') %}
   <ul>
   {% for level, deaths in scores.totalDeathCount.items() %}
       <li>{{ level }}: {{ deaths }} deaths</li>
   {% endfor %}
   </ul>

The full ``TableAccessor`` API — ``.rows``, ``.exports``, indexing, caching behavior — is in :doc:`/reference/participant_data_api`. The export-key syntax is in :doc:`/reference/custom_tables`.

Running expressions from templates
----------------------------------

``participant.evaluate(expr)`` runs an expression in the same DSL ``show_if`` and ``participant_calculations`` use. Useful for one-off calculations that are inconvenient to add to a questionnaire's ``participant_calculations`` block:

.. code-block:: html

   {% set total = participant.evaluate("scale_1 + scale_2 + scale_3") %}
   <p>Your composite score: {{ total }}.</p>

Returns ``None`` on parse error or when a referenced field doesn't exist. The full expression syntax is at :doc:`/reference/expressions`.

Session variables
-----------------

Flask's ``session`` is available in every template. BOFS populates it with five fields:

- ``session['participantID']`` — the current participant's ID.
- ``session['condition']`` — assigned condition number (1+, or 0 if unassigned).
- ``session['currentUrl']`` — the page the participant should be on.
- ``session['mTurkID']`` — the external ID (regardless of source: MTurk, Prolific, manual entry).
- ``session['code']`` — the completion code, populated near the end.

Branching on condition is the most common use:

.. code-block:: html

   {% if session.condition == 1 %}
       <p>Control instructions go here.</p>
   {% elif session.condition == 2 %}
       <p>Treatment instructions go here.</p>
   {% endif %}

Configuration access
--------------------

The project's TOML config is exposed as the ``config`` template variable. Access fields with bracket or attribute notation:

.. code-block:: html

   <p>Welcome to {{ config['TITLE'] }}.</p>
   <p>Contact: {{ config.SUPPORT_EMAIL }}</p>

Custom (non-BOFS) keys you set in ``config.toml`` are available the same way — useful for project-specific values you want to thread through templates without hard-coding them.

Reading data in custom blueprint routes
---------------------------------------

In a Python route, look up the participant by session ID:

.. code-block:: python

   from BOFS.globals import db
   from flask import session, render_template

   @my_blueprint.route("/results")
   @verify_correct_page
   @verify_session_valid
   def results():
       participant = db.Participant.query.get(session['participantID'])
       demo = participant.questionnaire('demographics')

       return render_template(
           "results.html",
           name=demo.first_name,
           condition_label=["Control", "Treatment"][session['condition'] - 1],
       )

The participant object you get from the database query has all the same methods (``questionnaire()``, ``table()``, ``evaluate()``, etc.) as the template variable.

Worked example: confirmation page
---------------------------------

A confirmation step that shows participants what they submitted before final review:

.. code-block:: html
   :caption: templates/simple/review.html

   {% extends "template.html" %}

   {% block contents %}
       {% set demo = participant.questionnaire('demographics') %}
       {% set survey = participant.questionnaire('survey') %}

       <h2>Please review your answers</h2>

       <h3>About you</h3>
       <ul>
           <li>Age: {{ demo.age }}</li>
           <li>Education: {{ demo.education }}</li>
       </ul>

       <h3>Survey responses</h3>
       <ul>
           <li>Question 1: {{ survey.q1 }}</li>
           <li>Question 2: {{ survey.q2 }}</li>
       </ul>

       <a href="/redirect_next_page">Looks good — continue</a>
       <a href="/redirect_to_page/questionnaire/survey">Go back and edit</a>
   {% endblock %}

Worked example: performance feedback from multiple sources
----------------------------------------------------------

A debrief page combining a questionnaire scale score, a custom-table aggregate, and a condition-specific message:

.. code-block:: html
   :caption: templates/simple/debrief.html

   {% extends "template.html" %}

   {% block contents %}
       {% set scores = participant.table('trial_data') %}
       {% set self_report = participant.questionnaire('post_task') %}

       <h2>Your results</h2>

       <p>You completed {{ scores.trial_count }} trials with an average reaction
       time of {{ scores.avg_rt | round(1) }} ms.</p>

       <p>You rated your effort {{ self_report.effort }} out of 7
       and your confidence {{ self_report.confidence }} out of 7.</p>

       {% if session.condition == 1 %}
           <p>Thank you for completing the control task.</p>
       {% else %}
           <p>The training task is part of an ongoing study —
           your data will help us refine the next version.</p>
       {% endif %}

       <a href="/redirect_next_page">Continue</a>
   {% endblock %}

See also
--------

- :doc:`/reference/participant_data_api` — exhaustive method reference.
- :doc:`/reference/expressions` — expression syntax for ``evaluate()`` and embedded ``{{ }}`` substitution.
- :doc:`/reference/custom_tables` — table definition format and export keys.
- :doc:`templates_jinja` — template lookup, blocks, override patterns.
- :doc:`blueprints_routes` — accessing participant data from a custom Python route.
