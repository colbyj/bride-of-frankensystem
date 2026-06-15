Recruiting via MTurk or Prolific
================================

Most of the wiring is the same across platforms: capture the participant's
ID from a URL parameter, optionally let them resume an interrupted session,
and either show a completion code or redirect them back to the platform when
they're done. The platform-specific parts are limited to URL formats and the
completion-redirect target.

For server deployment (TLS, reverse proxy, systemd), see :doc:`/deploying/server`.

External IDs
------------

An *external ID* is the participant identifier issued by the recruiting
platform (MTurk Worker ID, Prolific PID, etc.). BOFS stores it on the
``Participant.externalID`` column (also accessible as ``mTurkID``, an alias
kept for backward compatibility) regardless of which platform you use. There
are two ways to capture it.

**URL parameter (automatic).** When a participant arrives via a link that
includes a recognised parameter, BOFS stores it on the participant row at
consent without showing them anything. The recognised parameters are:

- ``PROLIFIC_PID`` — Prolific
- ``external_id`` — generic

A ``?source=`` URL parameter alongside lets you tag participants by
recruitment channel (e.g. ``?source=reddit``, ``?source=email``). The value
is free-form and lands on ``Participant.source``, where expression code can
branch on it (``show_if = "source == 'reddit'"``). When ``PROLIFIC_PID`` is
present without an explicit ``?source=``, BOFS infers ``source="prolific"``.

**Manual entry page.** Add the ``external_id`` page to your ``PAGE_LIST``
to prompt the participant to type their ID:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Participant ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]

With URL-parameter capture in place, this page is optional. It pre-fills
from the URL parameter if one was present, so include it only as a fallback
for participants who might arrive without one.

Customise the label and prompt shown on the manual entry page:

.. code-block:: toml

    EXTERNAL_ID_LABEL = "Your Platform Participant ID"
    EXTERNAL_ID_PROMPT = "Please enter the participant ID provided by the research platform."

The defaults provide a MTurk-specific prompt, so you will want to override
both when using Prolific or a generic platform. If you override `EXTERNAL_ID_PROMPT`, then
`EXTERNAL_ID_LABEL` will not be used.

.. image:: /examples/quickstart/page_external_id.png
   :width: 800
   :alt: The external ID page.

Session Management
------------------

Two settings control what happens when a participant returns with an external
ID that has already been seen:

.. code-block:: toml

    RETRIEVE_SESSIONS = true   # Resume incomplete sessions for known IDs
    ALLOW_RETAKES = false      # Prevent the same ID from completing twice

With ``RETRIEVE_SESSIONS = true``, BOFS checks each external ID against
existing participants, loads the previous session if it is incomplete, resumes
from the last completed page, and preserves the original condition assignment.
``ALLOW_RETAKES = false`` blocks a participant whose session is already marked
finished from starting again. These two together are the standard configuration
for crowdsourced studies: workers who closed their browser accidentally can
return and finish instead of being lost to attrition, but repeat submissions
are rejected.

For a deeper look at how session recovery works, see :doc:`/framework/sessions`.

Completion
----------

There are three options for how a participant's run ends.

**Generated completion code** — a unique code per participant:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy this completion code and paste it into the HIT to receive payment:"

BOFS generates a UUID-derived code automatically. Use this for MTurk, where
each worker pastes the code into the HIT form to claim payment. Because each
code is unique per participant, you can verify that a submitted code came from
someone who actually reached the end page.

**Static completion code** — the same code for everyone:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    STATIC_COMPLETION_CODE = "STUDY2024"
    COMPLETION_CODE_MESSAGE = "Your completion code is: STUDY2024"

**Redirect** — skip the code entirely and send the participant back to the
platform:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    OUTGOING_URL = "https://app.prolific.co/submissions/complete?cc=C1ABC123"

.. note::
   ``GENERATE_COMPLETION_CODE = true`` and ``OUTGOING_URL`` are mutually
   exclusive — only one of them takes effect.

.. image:: /examples/quickstart/page_end.png
   :width: 800
   :alt: The end page.

MTurk
-----

MTurk workers paste a completion code into the HIT form to claim payment,
so the generated-code approach is the standard fit.

**HIT URL.** When creating the HIT in MTurk, set the URL to pass the Worker
ID as a parameter:

.. code-block:: text

    https://yourdomain.com/consent?external_id=${mturk.workerId}

You can also leave the URL as ``https://yourdomain.com/consent`` and rely on
the manual ``external_id`` page if you prefer the worker to confirm their ID.

**Example TOML for MTurk:**

.. code-block:: toml

    TITLE = "Research Study"
    SQLALCHEMY_DATABASE_URI = "sqlite:///mturk_study.db"
    ADMIN_PASSWORD = "changeme"

    EXTERNAL_ID_LABEL = "MTurk Worker ID"
    EXTERNAL_ID_PROMPT = "Please enter your MTurk Worker ID exactly as it appears in your dashboard."

    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy this completion code and paste it into the MTurk HIT to receive payment:"

    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Worker ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]

If you want to redirect workers to MTurk's external-submit endpoint instead
of showing a code, set ``OUTGOING_URL`` to the MTurk submit URL and set
``GENERATE_COMPLETION_CODE = false``.

Prolific
--------

Prolific provides each study with a completion URL containing a completion
code. Participants must reach that URL for the platform to credit their
submission, so the redirect approach is the natural fit.

**Study URL.** Configure the Prolific study URL as:

.. code-block:: text

    https://yourdomain.com/consent?PROLIFIC_PID={{%PROLIFIC_PID%}}

BOFS picks up ``PROLIFIC_PID`` from the URL and stores it as the external ID.

**Example TOML for Prolific:**

.. code-block:: toml

    TITLE = "Research Study"
    SQLALCHEMY_DATABASE_URI = "sqlite:///prolific_study.db"
    ADMIN_PASSWORD = "changeme"

    EXTERNAL_ID_LABEL = "Prolific ID"
    EXTERNAL_ID_PROMPT = "Your Prolific ID should be automatically detected. If not, please enter it manually."

    GENERATE_COMPLETION_CODE = false
    OUTGOING_URL = "https://app.prolific.co/submissions/complete?cc=C1ABC123"

    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Prolific ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]

Replace ``C1ABC123`` with your study's actual completion code from Prolific.
If you want a custom completion page instead of an immediate redirect, leave
``OUTGOING_URL`` unset and override ``templates/end.html`` with
Prolific-specific instructions.

Security
--------

External IDs are personally identifiable. MTurk Worker IDs and Prolific PIDs
can be linked back to the participant's account and to other studies they have
participated in. They are stored in the database alongside the participant's
responses. Check your IRB's data-retention guidance and consider whether your
analysis pipeline needs to anonymise them before export.

The ``?source=`` parameter is self-reported and arrives unauthenticated in
the URL. A participant recruited from one channel can claim to be from
another by editing the URL. Treat ``source`` as a hint for filtering and
reporting, not as a credential. Where the distinction matters — for
example, per-source completion URLs that gate payment — gate on the
presence of a platform-issued parameter like ``PROLIFIC_PID``, not on the
``source`` string.

.. warning::
   Never commit ``ADMIN_PASSWORD`` to public version control.

Troubleshooting
---------------

**Debug mode** surfaces detailed error messages, request flow, and database
query logs, and adds a debug toolbar to the bottom of each page:

.. code-block:: bash

    BOFS run config.toml -d

**Admin panel.** The ``Participant`` table shows stored external IDs; the
``Progress`` table shows session flow. Watching for duplicate IDs there is
a fast way to catch configuration mistakes before they affect a live cohort.

Longitudinal studies
--------------------

For multi-session studies (e.g., a day-0 and day-1 wave), the standard
pattern is to capture ``PROLIFIC_PID`` on day 0 via ``RETRIEVE_SESSIONS``
and then look up the same participant on day 1 using ``CONDITIONS_FROM_DB``,
which reads the prior study's database to assign the returning participant
to the same condition they were in before — keeping the manipulation
consistent across waves.

See :doc:`/building/longitudinal` for a full walkthrough of this pattern,
including example TOML for both waves and how ``CONDITIONS_FROM_DB`` and
``CONDITIONS_FROM_CSV`` work.

See also
--------

- :doc:`/reference/configuration` — complete list of all TOML settings
- :doc:`/framework/sessions` — session lifecycle, ``RETRIEVE_SESSIONS``, ``ALLOW_RETAKES``
- :doc:`/building/longitudinal` — multi-wave studies with ``CONDITIONS_FROM_DB``
- :doc:`/deploying/server` — production deployment
