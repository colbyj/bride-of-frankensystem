Consent Forms
=============

BOFS provides four first-page route variants (with and without consent display, with and without condition assignment), a wrapper template you can override, and support for multi-stage consent. Two facts about the default flow matter for IRB protocols: the consent response itself is not persisted — only the existence of a ``Participant`` row indicates that consent was given — and declines leave no record at all. If your protocol requires a stored consent record or a reportable refusal rate, see `What happens on decline`_.

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

Four routes can sit at the top of ``PAGE_LIST``. They differ on two axes: whether ``consent.html`` is displayed, and whether a condition is assigned. The ``_nc`` suffix stands for "no condition."

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

For all four, the Participant row is created on first arrival (or first agreement, for the consent-displaying variants).

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

- **No participant row is created** for someone who declines. The consent flow is gated on agreement; there is no "declined" record to inspect later, so a consent or refusal rate cannot be computed from BOFS data alone.
- **The consent value itself is not persisted.** BOFS uses the radio choice to gate the form submission; once a participant agrees and the row is created, only the existence of the row indicates consent. The participant's ``timeStarted`` is the closest equivalent to a "consent timestamp."

If your IRB requires a stored record of each consent, collect it as a one-question questionnaire after the consent page (see `Multi-stage consent`_). If you also need to record declines, the built-in consent page cannot do it — decliners never advance past it. Instead, start the study with ``create_participant_nc``, present the consent text as a questionnaire whose answer *is* stored, and use ``conditional_routing`` (see :doc:`/building/conditions_branching`) to send decliners to an exit page.

Writing consent.html
--------------------

The file contains your consent text — BOFS adds the radio buttons and Continue button around it. A minimal example:

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

To link a downloadable PDF copy, place ``consent.pdf`` in your project's ``static/`` directory and link it at ``/static/consent.pdf``. Static files are served at ``/static/<filename>``.

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

The secondary response *is* recorded (questionnaire submissions persist, unlike the primary consent radios) and appears in the admin export like any other questionnaire — no code needed. From templates or Python it is accessible via ``participant.questionnaire("media_release")``. This is the practical workaround if you need an audit trail for a specific consent decision.

Customizing the consent wrapper
-------------------------------

To change the agree/decline wording, the button text, or the layout of the form BOFS wraps around your ``consent.html``, override the wrapper template by creating ``templates/consent.html`` in your project (note: ``consent.html`` *and* ``templates/consent.html`` are different — the first is your study's consent text, the second overrides the wrapper). See :doc:`/framework/templates_jinja` for template lookup order and override patterns.

See also
--------

- :doc:`/reference/configuration` for consent-adjacent settings (``GENERATE_COMPLETION_CODE``, ``ADMIN_PASSWORD``, ``EXTERNAL_ID_*``).
- The `minimal example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/minimal_example>`_ for the default consent flow in context.
