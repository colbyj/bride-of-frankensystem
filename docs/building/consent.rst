Consent Forms
=============

Consent looks like a single checkbox on the surface and isn't. BOFS offers four first-page route variants, lets you customize the wrapper template, supports multi-stage consent for media releases or debrief acknowledgements, and has a few quirks researchers tend to discover the hard way (e.g., the consent response itself isn't persisted — see below). This page covers all of it.

Why this has its own page
-------------------------

Required for human-subjects research; an IRB amendment is the cost of getting the consent flow wrong. The defaults work, but the right variant for your study depends on whether you're collecting consent in BOFS at all, whether you're assigning conditions, and whether you have additional consents to record.

The default consent flow
------------------------

When ``PAGE_LIST`` starts with ``{name="Consent", path="consent"}``, BOFS:

1. Renders ``consent.html`` from your project root, wrapped in a form with two radio options ("I give my consent" / "I do not give my consent") and a Continue button.
2. On submission, validates that the participant chose to consent.
3. If they consented, creates a ``Participant`` row, assigns a condition (if any are configured), and routes them to the next page in ``PAGE_LIST``.
4. If they declined, the form fails validation with a message and the participant cannot continue. No row is created and the consent value itself is not stored anywhere.

A minimal ``consent.html`` looks like:

.. code-block:: html

   <h1>My Study</h1>
   <h2>Consent to Participate</h2>
   <p>You are invited to participate in a study about ...</p>
   <p><strong>Principal Investigator:</strong> Dr. Example, Department of Examples</p>
   <p><strong>IRB Approval:</strong> 2026-001</p>

The radios and Continue button are added by BOFS — your file holds only the consent text.

Choosing a first-page route
---------------------------

Four routes can sit at the top of ``PAGE_LIST``. They differ on two axes: whether ``consent.html`` is displayed, and whether a condition is assigned.

.. list-table::
   :header-rows: 1
   :widths: 30 18 18 34

   * - Route
     - Shows consent.html?
     - Assigns condition?
     - Use when
   * - ``consent``
     - Yes
     - Yes
     - The default. Online recruitment with conditions.
   * - ``consent_nc``
     - Yes
     - No
     - You collect consent in BOFS but conditions are assigned later (or not at all).
   * - ``create_participant``
     - No
     - Yes
     - Consent collected externally (e.g., paper consent in a lab session). Participant arrives at the URL after already consenting.
   * - ``create_participant_nc``
     - No
     - No
     - Consent collected externally and no conditions, or conditions assigned later via ``assign_condition``.

The ``_nc`` suffix stands for "no condition." For all four, the Participant row is created on first arrival (or first agreement, for the consent-displaying variants).

Picking the variant is a one-line change in ``PAGE_LIST``:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent", path="consent_nc"},     # show consent, no condition
       {name="Survey",  path="questionnaire/survey"},
       {name="End",     path="end"}
   ]

What happens on decline
-----------------------

Declining the consent radio fails the form's required-field validation. The participant sees the form re-rendered with an error message ("You must provide your consent to continue"). They cannot advance, and closing the tab is their exit.

Two consequences worth being explicit about:

- **No participant row is created** for someone who declines. The consent flow is gated on agreement; there is no "declined" record to inspect later.
- **The consent value itself is not persisted.** BOFS uses the radio choice to gate the form submission; once a participant agrees and the row is created, only the existence of the row indicates consent. The participant's ``timeStarted`` is the closest equivalent to a "consent timestamp."

If your IRB requires an explicit decline log or a stored consent record, you can collect it as a one-question questionnaire after consent (e.g., ``questionnaire/explicit_consent``).

Writing consent.html
--------------------

The file should contain the actual text the IRB approved — purpose, procedures, risks, benefits, confidentiality, voluntary participation, contact information. Common patterns:

.. code-block:: html

   <h1>Study Title</h1>
   <p><strong>Principal Investigator:</strong> Name (email)</p>
   <p><strong>IRB Approval:</strong> 2026-001</p>

   <h3>Purpose</h3>
   <p>...</p>

   <h3>Procedures</h3>
   <p>...</p>

   <h3>Contact for questions</h3>
   <p>...</p>

   <p>For your records, a downloadable copy of this consent form is available
   <a href="/static/consent.pdf">here</a>.</p>

The PDF link works if you put ``consent.pdf`` in your project's ``static/`` directory. Static files are served at ``/static/<filename>``.

Multi-stage consent
-------------------

Studies that record additional consents (media release, debrief acknowledgement, second-language consent) usually add a follow-up page after the main consent. The follow-up is a regular page in ``PAGE_LIST`` — typically a ``simple/`` page or a one-question questionnaire:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",        path="consent"},
       {name="Media Release",  path="questionnaire/media_release"},
       {name="Demographics",   path="questionnaire/demographics"},
       {name="End",            path="end"}
   ]

The secondary response *is* recorded (questionnaire submissions persist, unlike the primary consent radios) and is accessible via ``participant.questionnaire("media_release")``. This is the practical workaround if you need an audit trail for a specific consent decision.

Customizing the consent wrapper
-------------------------------

To change the agree/decline wording, the button text, or the layout of the form BOFS wraps around your ``consent.html``, override the wrapper template by creating ``templates/consent.html`` in your project (note: ``consent.html`` *and* ``templates/consent.html`` are different — the first is your study's consent text, the second overrides the wrapper). See :doc:`/framework/templates_jinja` for template lookup order and override patterns.

IRB practical notes
-------------------

- **Versioning consent text across IRB amendments.** If the consent text changes mid-study, don't quietly overwrite ``consent.html`` — participants who already submitted saw the old version. Either start a new project, copy the consent file (``consent_v2.html``) and switch, or version-control the file with git so the diff is recoverable.
- **What's actually in the database.** As noted above, consent itself isn't a column on the Participant row. If your IRB expects a per-participant audit field, add a one-question follow-up (``"Did you consent?"`` ``"Yes"``) and the response will be stored normally.
- **The consent page must be the first page in ``PAGE_LIST``.** ``consent``, ``consent_nc``, ``create_participant``, and ``create_participant_nc`` are the only valid first-page routes. Putting any of them later in the list, or omitting them entirely, won't work — see :doc:`page_flow` for the full required-routes rules.

See also
--------

- :doc:`/reference/configuration` for consent-adjacent settings (``GENERATE_COMPLETION_CODE``, ``ADMIN_PASSWORD``, ``EXTERNAL_ID_*``).
- The `minimal example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/minimal_example>`_ for the default consent flow in context.
