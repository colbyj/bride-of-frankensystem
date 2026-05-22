Longitudinal Experiments
========================

A longitudinal study has the same participant returning across multiple sessions — hours, days, or weeks apart — and answering related questions or doing related tasks each time. Examples: a baseline survey followed by a one-week follow-up, a four-day diary study, a learning task with a 24-hour retention test.

BOFS supports two shapes for this. They share the same building blocks — a stable external ID and a database that persists between visits — but differ in whether each visit runs through the same ``PAGE_LIST`` or whether each session is its own deployment.

.. grid:: 2
    :gutter: 2

    .. grid-item-card::  Pattern A — Same PAGE_LIST, repeated visits

        A single ``config.toml`` describing one visit's flow. When the participant returns with the same external ID, BOFS creates a new participant row but carries their condition forward, so they run through the same flow again as the same group.

        Suits diary studies, daily check-ins, weekly mood surveys, or any design where every visit asks the same questions.

    .. grid-item-card::  Pattern B — Separate per-session deployments

        A ``day1.toml`` and ``day2.toml`` (and possibly more), each with its own ``PAGE_LIST`` and its own database. Day 2 is a fresh session; BOFS uses the external ID to recover the participant's prior condition assignment from day 1's database (or a CSV).

        Suits two-part studies where day 2's content differs from day 1's, separate recruitment links per session (e.g. a Prolific follow-up study), or longer gaps where you want each session's data isolated.

The longitudinal example linked at the bottom of this page is built as Pattern B. The rest of this page covers what each pattern needs and what they have in common.

How returning participants are recognized
-----------------------------------------

Both patterns need a stable identifier the participant brings back with them. BOFS supports three sources:

- **A URL parameter.** When a participant arrives at ``http://your-study.example/?external_id=abc123``, BOFS captures the value in the session as ``externalID`` (also accessible as ``mTurkID``, an alias kept for backward compatibility — both keys are written together). Recruitment platforms like Prolific append the participant ID automatically — Prolific's ``PROLIFIC_PID`` parameter is also captured.
- **A manual entry page.** Adding ``{name="Enter ID", path="external_id"}`` to ``PAGE_LIST`` shows a form asking the participant to type their ID. Customizable via ``EXTERNAL_ID_LABEL`` and ``EXTERNAL_ID_PROMPT``. With URL-parameter capture in place this page is optional — include it only as a fallback for participants who arrive without a platform-provided ID.
- **A blueprint route you write.** For custom recruitment flows, a Python view can call ``set_external_id_in_session(value)`` (from ``BOFS.util``) to populate the external ID. Existing code that writes ``session['mTurkID']`` directly still works.

For details, see :doc:`/deploying/recruiting`.

Pattern A — Same PAGE_LIST, repeated visits
-------------------------------------------

Two configuration settings drive this:

- ``RETRIEVE_SESSIONS = true`` — when a participant returns with the same external ID, BOFS looks up their past attempts and copies the prior condition forward into the new session.
- ``ALLOW_RETAKES = true`` — lets a participant who already finished start a fresh attempt. With ``ALLOW_RETAKES = false``, a finished participant who returns is restored to their finished state and shown the end page again, so they can't run through the flow a second time.

Each return creates a new ``Participant`` row sharing the same ``externalID``. All rows for that participant accumulate in the same database — questionnaire responses, custom-table rows, timestamps. The ``Participant.timeStarted`` column distinguishes attempts; admin-panel exports group by external ID.

Because each visit is its own participant row, the same questionnaire submitted on visit 1 and visit 2 doesn't collide — they're separate rows in the questionnaire's table, distinguishable by ``participantID`` and timestamp. No tagging required.

.. note::

   **Repeated measures within a single visit.** If you instead need the same questionnaire administered twice in *one* run through ``PAGE_LIST`` (e.g. a pre-test and post-test on the same day), use the ``tag`` field on each ``PAGE_LIST`` entry — that's a separate mechanism from longitudinal returns. See :ref:`repeated-questionnaires` in the page-flow reference.

For the underlying session lifecycle and the IP-binding interaction, see :doc:`/framework/sessions`.

Pattern B — Separate per-session deployments
--------------------------------------------

Each session runs as its own BOFS instance with its own ``config.toml``, its own ``PAGE_LIST``, and its own database. A typical day-2 configuration:

.. code-block:: toml

   SQLALCHEMY_DATABASE_URI = 'sqlite:///day2.db'

   RETRIEVE_SESSIONS = true
   ALLOW_RETAKES = false

   # Look up the returning participant in day 1's database and reuse their condition.
   CONDITIONS_FROM_DB = 'sqlite:///day1.db'

   CONDITIONS = [
       {label="Linear Menu",  enabled=true},
       {label="Marking Menu", enabled=true}
   ]

   PAGE_LIST = [
       {name="Consent",        path="consent_nc"},
       {name="Participant ID", path="external_id"},
       {name="",               path="assign_condition"},
       # ... day-2 content ...
       {name="End",            path="end"}
   ]

Three things are unique to Pattern B:

- **Carrying conditions across deployments.** Either ``CONDITIONS_FROM_DB`` or ``CONDITIONS_FROM_CSV`` tells day 2 where to look up the condition assigned on day 1. ``CONDITIONS`` itself must list the same conditions in the same order as the source — the lookup is by integer position.

  - ``CONDITIONS_FROM_DB = '<sqlalchemy-uri>'`` — points at another BOFS database (typically day 1's). The returning participant's external ID is matched against the ``Participant`` table there and their condition is reused.
  - ``CONDITIONS_FROM_CSV = "path/to/file.csv"`` — pre-assigns conditions from a CSV file keyed by external ID (two columns: external ID, condition number). Useful when condition assignment is decided outside BOFS. If both ``CONDITIONS_FROM_CSV`` and ``CONDITIONS_FROM_DB`` are set, the CSV is consulted first and the DB is the fallback.

- **Consent without re-randomizing.** Plain ``consent`` runs condition assignment at submission time, which would burn a random condition on day 2 before the external ID had been collected. Use ``consent_nc`` (no condition) on day 2 instead.

- **Explicit ``assign_condition`` after the external ID.** Place ``{name='', path='assign_condition'}`` *after* ``external_id`` in ``PAGE_LIST`` so the lookup has something to match on. A participant entering an unrecognized ID is shown an "ID Not Recognized" page and cannot proceed.

``RETRIEVE_SESSIONS`` is still useful within each deployment — if a participant drops off partway through day 2 and returns later, BOFS resumes them in day-2's ``PAGE_LIST``. ``ALLOW_RETAKES`` should usually stay ``false`` for the same reason as in Pattern A.

For the underlying lifecycle and the IP-binding interaction, see :doc:`/framework/sessions`.

Branching by prior responses
----------------------------

Page-level ``show_if`` predicates and ``conditional_routing`` blocks both operate on the *current* participant row. ``has_questionnaire('survey')`` checks the rows on the participant currently in session — it will not see questionnaire submissions from a prior visit (Pattern A, separate participant row) or from a prior deployment (Pattern B, separate database).

To branch on cross-visit data, query it from a custom blueprint route — for Pattern A, by external ID against the same database; for Pattern B, by external ID against day 1's database (the same one ``CONDITIONS_FROM_DB`` points at). Branching by the ``condition`` value works in both patterns, since the condition is carried forward.

The expression syntax is described in :doc:`/reference/expressions`. The full branching pattern is in :doc:`conditions_branching`.

Storing custom task data across sessions
----------------------------------------

Custom tables defined in ``tables/*.json`` accumulate rows across sessions. Every row carries the participant's ``participantID`` and a ``timeSubmitted`` timestamp. See :doc:`storing_custom_data`.

In Pattern A, each visit is a separate ``participantID``, so rows naturally separate by visit — group by ``participantID`` then look up the shared ``externalID`` on the ``Participant`` table to combine across visits. In Pattern B, custom-table data lives in each deployment's own database, so analysis that spans days requires reading from both.

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
- **Faking a return (Pattern A).** Complete the flow with ``external_id=test1``, then reload with the same external ID — a new participant row is created, the prior condition is carried forward, and you can run through the flow again.
- **Running both deployments side by side (Pattern B).** Start each ``.toml`` in its own terminal: ``BOFS run day1.toml -d`` on one port, ``BOFS run day2.toml -d`` on another. Complete a participant in day 1 first so day 2's ``CONDITIONS_FROM_DB`` lookup has something to find.

See also
--------

- The `longitudinal example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/longitudinal_example>`_ — a two-day HCI menu-learning study built as Pattern B, using ``CONDITIONS_FROM_DB`` to carry condition from day 1 to day 2. The example also includes a ``conditions.csv`` to demonstrate the ``CONDITIONS_FROM_CSV`` alternative.
