MTurk and Prolific Integration
==============================

This guide covers how to configure a BOFS project for recruiting through Amazon Mechanical Turk or Prolific. Most of the wiring is the same across platforms — capturing the participant's ID from a URL parameter, optionally letting them resume an interrupted session, and either showing a completion code or redirecting them back to the platform when they're done. The platform-specific parts are limited to URL formats and the completion-redirect target.

For server deployment (TLS, systemd, Nginx), see :doc:`server_config`.

External IDs
------------

An *external ID* is the participant identifier issued by the recruiting platform (MTurk Worker ID, Prolific PID, etc.). BOFS can capture it two ways.

**1. URL parameter (automatic).** When a participant arrives via a link that includes a known parameter, BOFS picks it up without showing them anything. The recognised parameters are:

- ``external_id`` — generic
- ``PROLIFIC_PID`` — Prolific
- ``mTurkID`` — MTurk (legacy)

**2. Manual entry page.** Add the ``external_id`` page to your ``PAGE_LIST`` and BOFS prompts the participant to type their ID:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Participant ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]

When a known URL parameter is present, the manual page pre-fills the field with it, so it's safe to include the page either way.

Customise the label and prompt:

.. code-block:: toml

    EXTERNAL_ID_LABEL = "Your Platform Participant ID"
    EXTERNAL_ID_PROMPT = "Please enter the participant ID provided by the research platform."

.. image:: /examples/quickstart/page_external_id.png
  :width: 800
  :alt: The external ID page.

Session Management
------------------

Two settings control what happens when a participant returns with an external ID that's already been seen:

.. code-block:: toml

    RETRIEVE_SESSIONS = true   # Resume incomplete sessions for known IDs
    ALLOW_RETAKES = false      # Prevent the same ID from completing twice

With ``RETRIEVE_SESSIONS = true``, BOFS checks each external ID against existing participants, loads the previous session if it's incomplete, resumes from the last completed page, and preserves the original condition assignment. The combination above is the right default for crowdsourced studies — it lets workers who closed their browser come back, while preventing repeat submissions.

Completion
----------

There are three options for how a participant's run ends, configured in TOML:

**Generated completion code** (a unique code per participant):

.. code-block:: toml

    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy this completion code and paste it into the HIT to receive payment:"

BOFS generates a UUID-derived code automatically.

**Static completion code** (the same code for everyone):

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    STATIC_COMPLETION_CODE = "STUDY2024"
    COMPLETION_CODE_MESSAGE = "Your completion code is: STUDY2024"

**Redirect** (skip the code entirely and send the participant back to the platform):

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    OUTGOING_URL = "https://app.prolific.co/submissions/complete?cc=C1ABC123"

.. note::
    ``GENERATE_COMPLETION_CODE = true`` and ``OUTGOING_URL`` are mutually exclusive — pick one.

.. image:: /examples/quickstart/page_end.png
  :width: 800
  :alt: The end page.

MTurk
-----

For MTurk you typically want a generated completion code (workers paste it into the HIT to claim payment).

**HIT URL.** When creating the HIT in MTurk, set the URL to pass the Worker ID as a parameter:

.. code-block:: text

    https://yourdomain.com/consent?external_id=${mturk.workerId}

You can also leave it as ``https://yourdomain.com/consent`` and rely on the manual ``external_id`` page if you'd rather have the worker confirm their ID.

**Example TOML for MTurk:**

.. code-block:: toml

    TITLE = "Research Study - MTurk"
    SQLALCHEMY_DATABASE_URI = "sqlite:///mturk_study.db"
    ADMIN_PASSWORD = "secure_admin_password"

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

If you want to redirect workers back to MTurk's external-submit endpoint instead of showing a code, set ``OUTGOING_URL`` to the MTurk submit URL and disable the generated code.

Prolific
--------

Prolific provides each study with a completion URL containing the study's completion code. Participants must hit that URL for the platform to credit their submission, so the redirect approach is the natural fit.

**Study URL.** Configure the Prolific study URL as:

.. code-block:: text

    https://yourdomain.com/consent?PROLIFIC_PID={{%PROLIFIC_PID%}}

BOFS picks up ``PROLIFIC_PID`` automatically and stores it as the external ID.

**Example TOML for Prolific:**

.. code-block:: toml

    TITLE = "Research Study - Prolific"
    SQLALCHEMY_DATABASE_URI = "sqlite:///prolific_study.db"
    ADMIN_PASSWORD = "secure_admin_password"

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

Replace ``C1ABC123`` with your study's actual completion code from Prolific. If you want a custom completion page instead of an immediate redirect, leave ``OUTGOING_URL`` unset and override ``templates/end.html`` with Prolific-specific instructions.

Security
--------

External IDs are personally identifiable. MTurk Worker IDs and Prolific PIDs in particular can be linked back to the participant's account and other studies they've taken part in. They're stored in the database alongside the participant's responses, so check your IRB's guidance on retention and consider whether your analysis pipeline needs to anonymise them.

.. warning::
    Never commit ``ADMIN_PASSWORD`` to public version control.

Troubleshooting
---------------

**Debug mode** surfaces detailed error messages, request flow, and database query logs:

.. code-block:: bash

    BOFS run config.toml -d

The browser also gets a debug toolbar at the bottom of each page during ``-d`` runs.

**Admin panel** is the fastest way to verify external IDs are being captured and sessions are being recovered correctly. Check the ``Participant`` table for stored IDs and the ``Progress`` table for session flow. Watching for duplicate IDs there is a good way to catch configuration mistakes before they affect a real cohort.
