Data Quality
============

Every online study collects some responses you'd rather leave out: submissions from automated bots, the same person participating more than once, and answers given too carelessly or quickly to be usable. BOFS offers several ways to reduce and detect these; some run automatically, others you turn on when your study needs them.

Automatic bot screening
-----------------------

Two protections run on every study with no configuration.

**User-agent check.** BOFS checks each new participant's user agent against a list of known web crawlers (automated programs that visit pages, such as search-engine indexers). A visitor that matches is flagged and left out of condition-balancing counts.

**Honeypot field.** The consent page includes a decoy text field hidden from view. A person filling out the form never sees it, but some automated bots fill in every field they find. If the decoy input is given a value, BOFS treats the submission as a bot and does not create a participant.

These checks are not foolproof. A determined bot can spoof a normal user agent and skip hidden fields. However, they do exclude some automated traffic (such as web crawlers) without affecting real participants.

Logging how participants respond
--------------------------------

BOFS can record *how* a participant fills out each questionnaire, not just their final answers. This is off by default. Turn it on in your config:

.. code-block:: toml

   LOG_QUESTIONNAIRE_INTERACTIONS = true

.. note::

   Earlier versions called this setting ``LOG_GRID_CLICKS``. The old name still works, but ``LOG_QUESTIONNAIRE_INTERACTIONS`` is the current spelling.

With logging on, BOFS records a timestamped event each time a participant interacts with a questionnaire input. The event types are:

- ``focus`` and ``blur`` — entering and leaving an input.
- ``change`` — a changed answer.
- ``paste`` — text pasted into a field (rather than typed).
- ``drop`` — text dragged and dropped into a field (rather than typed).
- ``visibility`` — the browser tab being hidden or shown, which happens when the participant switches away to another tab or window.

Together these let you measure how much time participants spent on each item, whether they revised answers, whether they pasted responses in, and whether they left the page mid-questionnaire. These signals can be used to gauge attentiveness and effort.

To get the data, open the admin **Export** page and download the questionnaire interaction log (see :doc:`monitoring_data`). It is a flat table with one row per event: ``participantID``, ``externalID``, ``questionnaire``, ``tag``, ``questionID``, ``eventType``, ``timestamp``, and ``value``.

.. note::

   The ``value`` column records the input's contents at the time of the event, so the log can contain participants' own responses. Treat it as participant data: store and share it under the same conditions as the rest of your dataset, and check your IRB's guidance before exporting.

Preventing repeat submissions
-----------------------------

When you recruit with a participant identifier (a Prolific or MTurk ID, or a code you assign), BOFS can keep the same person from completing the study twice. Setting ``ALLOW_RETAKES = false`` blocks an identifier that has already finished from starting a fresh attempt, while ``RETRIEVE_SESSIONS = true`` lets someone who was interrupted resume where they left off. This catches repeat submissions from the same identifier; it does not catch one person returning under a new identifier. The full behaviour is described in :doc:`/deploying/recruiting` and :doc:`/framework/sessions`.

Keeping participants engaged with materials
-------------------------------------------

Two questionnaire features help ensure participants actually engage with what you present:

- **Required questions** (``"required": true``) prevent a participant from advancing past a question they have left blank. See :doc:`adding_survey_questions`.
- **Force-watch media** (``"force_watch": true`` on a ``video`` or ``audio`` question) keeps the Continue button disabled until a video clip has been played. See :doc:`/reference/question_types`.
- **Disabling paste** stops participants from pasting (or dragging) text into a field, so free-text answers have to be typed. Set ``DISABLE_PASTE = true`` in your config to apply this to every text input across the study, or set ``"disable_paste": true`` on an individual text question to apply it to just that question. When interaction logging is on, blocked paste and drop attempts are still recorded.

Reviewing and excluding participants
------------------------------------

After data collection, the admin panel helps you spot and remove low-quality records:

- **Completion times.** The progress page reports each participant's duration, by condition (see :doc:`monitoring_data`).
- **Abandoned participants.** Participants who go inactive past ``ABANDONED_MINUTES`` are flagged as abandoned and left out of condition balancing (see :doc:`/framework/sessions`).
- **Manual exclusion.** The progress page has a per-participant exclusion checkbox, and the export can omit excluded or unfinished participants (see :doc:`monitoring_data`).
