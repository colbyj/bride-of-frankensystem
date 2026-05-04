Longitudinal Experiments
========================

A longitudinal study has the same participant returning across multiple sessions — hours, days, or weeks apart — and answering related questions or doing related tasks each time. Examples: a baseline survey followed by a one-week follow-up, a four-day diary study, a learning task with a 24-hour retention test.

In BOFS terms, "longitudinal" means three things working together: a way to recognize the returning participant, a way to resume them in the right place, and a way to record the same questionnaires multiple times without overwriting prior data. This page describes how each of those works.

How returning participants are recognized
-----------------------------------------

Every returning participant needs a stable identifier they bring back with them. BOFS supports three sources:

- **A URL parameter.** When a participant arrives at ``http://your-study.example/?external_id=abc123``, BOFS captures the value in the session as ``mTurkID`` (the field is named for historical reasons but applies to any external ID). Recruitment platforms like Prolific append the participant ID automatically — Prolific's ``PROLIFIC_PID`` parameter is also captured.
- **A manual entry page.** Adding ``{name="Enter ID", path="external_id"}`` to ``PAGE_LIST`` shows a form asking the participant to type their ID. Customizable via ``EXTERNAL_ID_LABEL`` and ``EXTERNAL_ID_PROMPT``.
- **A blueprint route you write.** For custom recruitment flows, a Python view can populate ``session['mTurkID']`` directly.

For details, see :doc:`/deploying/recruiting`.

Resuming a returning participant
--------------------------------

Two configuration settings control session recovery:

- ``RETRIEVE_SESSIONS = true`` — when a participant returns with the same external ID, BOFS finds their prior session and restores it. They pick up wherever they left off in ``PAGE_LIST``.
- ``ALLOW_RETAKES`` — controls what happens for participants who already finished. ``false`` (the default) blocks repeat completions; ``true`` lets a finished participant start over from the beginning.

For multi-session studies, ``RETRIEVE_SESSIONS`` should be ``true`` so day-2 participants don't restart from consent. ``ALLOW_RETAKES`` is usually ``false`` — you don't want a participant accidentally double-completing the day-1 portion when they meant to start day 2.

For the underlying lifecycle and the IP-binding interaction, see :doc:`/framework/sessions`.

Repeating the same questionnaire across sessions
------------------------------------------------

A pre/post or day-1/day-7/day-14 design uses the same questionnaire JSON multiple times. ``PAGE_LIST`` lists each occurrence with a different ``tag``:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",        path="consent"},
       {name="Mood (day 1)",   path="questionnaire/mood",  tag="day1"},
       {name="Task (day 1)",   path="custom/task"},
       # ... (participant comes back next day) ...
       {name="Mood (day 2)",   path="questionnaire/mood",  tag="day2"},
       {name="End",            path="end"}
   ]

Each tagged submission is a separate row in the questionnaire's database table. To read a specific tagged response from a template or blueprint route:

.. code-block:: html

   {% set day1 = participant.questionnaire("mood", "day1") %}
   {% set day2 = participant.questionnaire("mood", "day2") %}
   <p>Your day-1 score was {{ day1.score }}; your day-2 score is {{ day2.score }}.</p>

For the full participant API, see :doc:`/framework/participant_data`.

Carrying conditions across sessions
-----------------------------------

If your study assigns conditions on day 1, the day-2 participant must end up in the same condition. Two configuration settings handle this; pick one:

- ``CONDITIONS_FROM_DB = true`` — looks up the returning participant by external ID in the project's own participant database and reuses their prior condition. No external file required.
- ``CONDITIONS_FROM_CSV = "path/to/file.csv"`` — pre-assigns conditions from a CSV file keyed by external ID. The CSV has two columns (external ID, condition number) and is read at startup. Useful when you want condition assignment decided outside BOFS.

A typical day-2 ``config.toml`` uses one or the other:

.. code-block:: toml

   RETRIEVE_SESSIONS = true
   ALLOW_RETAKES = false
   CONDITIONS_FROM_DB = true

   CONDITIONS = [
       {label="Linear Menu",  enabled=true},
       {label="Marking Menu", enabled=true}
   ]

Branching by session or prior responses
---------------------------------------

To skip pages the participant already completed, or run different content based on prior answers, use page-level ``show_if``:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",     path="consent"},
       {name="Recall test", path="questionnaire/recall", show_if="has_questionnaire('mood', 'day1')"},
       {name="End",         path="end"}
   ]

The expression syntax — including how to reference tagged questionnaires, custom-table exports, and the ``condition`` value — is described in :doc:`/reference/expressions`. The full pattern is in :doc:`conditions_branching`.

Storing custom task data across sessions
----------------------------------------

Custom tables defined in ``tables/*.json`` accumulate rows across sessions. Every row is automatically tagged with the participant's ``participantID`` and a ``timeSubmitted`` timestamp. Filtering by ``timeSubmitted`` (or by a session-name column you add yourself) lets you separate day-1 from day-2 trials. See :doc:`storing_custom_data`.

Bringing participants back
--------------------------

This part is out of scope for BOFS. Email reminders, scheduling, calendar invites, and SMS notifications need to come from outside the framework. The practical pattern is:

1. Export the participant ID list from the admin panel after day 1.
2. Send each participant a reminder (email, SMS, recruitment-platform message) with the study URL and their external ID.
3. They click the link, the URL parameter populates the external ID, and BOFS recognizes them.

Recruitment platforms (Prolific, MTurk) handle this for you — Prolific in particular has built-in support for two-part studies that auto-message participants.

Testing during development
--------------------------

Walking through a multi-session flow on your own machine takes a bit of setup:

- **Inspecting a participant's progress.** The admin panel's participant detail view shows the current page, the questionnaires submitted, and the timestamps. Use it to confirm a returning session resumed at the right spot.
- **Faking a return.** Set ``ALLOW_RETAKES = true`` temporarily, complete the day-1 flow with ``external_id=test1``, then reload with the same external ID — you'll be treated as a returning participant. Set ``ALLOW_RETAKES`` back to ``false`` for production.
- **Multiple TOML files.** A common pattern is to keep ``day1.toml`` and ``day2.toml`` configurations side by side, each with a different ``PAGE_LIST``, sharing the same database. ``BOFS run day1.toml -d`` and ``BOFS run day2.toml -d`` simulate the two arrival contexts.

See also
--------

- The `longitudinal example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/longitudinal_example>`_ — a two-day HCI menu-learning study using ``CONDITIONS_FROM_DB``, with day-0 randomization and day-1 lookup by Prolific ID. The example also demonstrates the ``CONDITIONS_FROM_CSV`` alternative.
