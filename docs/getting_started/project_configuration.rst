Configuring Your Experiment
===========================

A BOFS experiment is configured by a single TOML file — typically ``config.toml`` — that defines the page sequence, database connection, condition assignment, completion handling, and so on. This page covers the configuration concepts you'll use most often. The full setting-by-setting reference lives in :doc:`../reference/config_options`.

TOML uses a plain key-value format with ``#`` for comments and ``[brackets]`` for lists:

.. code-block:: toml

    TITLE = "My Research Study"

    # Comments start with #.

    CONDITIONS = [
        {label="Control", enabled=true},
        {label="Treatment", enabled=true}
    ]

Basic Configuration Structure
-----------------------------

Every BOFS project needs a configuration file (typically named ``config.toml``) with these essential settings:

.. code-block:: toml

    # Basic project information
    TITLE = "My Research Study"
    PORT = 5000

    # Database connection
    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"

    # Admin access
    ADMIN_PASSWORD = "secure_admin_password"

    # Page sequence (covered in detail below)
    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="End", path="end"}
    ]

**Required Settings**

=========================== =======================================================
Setting                     Description
=========================== =======================================================
**TITLE**                   Study name (shown in browser tab and admin panel)
**PORT**                    The port that your experiment will run on (e.g., the "5000" in http://localhost:5000)
**SQLALCHEMY_DATABASE_URI** Database connection (use SQLite for development)
**ADMIN_PASSWORD**          Password for accessing admin panel at ``/admin``
**PAGE_LIST**               The sequence of pages that participants will encounter
=========================== =======================================================

Defining Experiment Flow with PAGE_LIST
----------------------------------------

The ``PAGE_LIST`` is the heart of your experiment configuration. It defines the exact sequence of pages participants will see, in order.

**Basic Structure**

Each page in the list has two required properties:

.. code-block:: toml

    PAGE_LIST = [
        {name="Display Name", path="route/path"},
        {name="Another Page", path="different/route"}
    ]

- ``name``: Human-readable name (shown in admin panel and progress tracking)
- ``path``: URL route that determines what content to display

**Required Start and End Pages**

Every experiment must have:

1. **First page**: One of these participant creation routes:

   - ``consent`` - Shows consent form, creates participant, assigns condition
   - ``consent_nc`` - Shows consent form, creates participant, NO condition assignment
   - ``create_participant`` - Creates participant and assigns condition (no consent form)
   - ``create_participant_nc`` - Creates participant with NO condition assignment

2. **Last page**: Must be ``end`` - Shows completion message and/or completion code

**Minimal Example**

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="End", path="end"}
    ]

**Page Types Available**

======================= ===============================================
Path Format             Description
======================= ===============================================
``consent``             Built-in consent form with participant creation
``external_id``         Collect external ID (MTurk Worker ID, etc.)
``questionnaire/name``  Display questionnaire from ``questionnaires/name.json``
``instructions/name``   Show instruction page from ``templates/instructions/name.html``
``simple/name``         Show custom HTML page from ``templates/simple/name.html``
``custom_route``        Your custom blueprint routes
``end``                 Built-in completion page
======================= ===============================================

**Complete Example**

.. code-block:: toml

    PAGE_LIST = [
        # Participant setup
        {name="Consent", path="consent"},
        {name="External ID", path="external_id"},
        
        # Demographics and instructions  
        {name="Demographics", path="questionnaire/demographics"},
        {name="Task Instructions", path="instructions/task_intro"},
        
        # Main experimental tasks
        {name="Practice Trials", path="task/practice"},
        {name="Main Task", path="task/experiment"},
        
        # Post-task measures
        {name="Task Questionnaire", path="questionnaire/post_task"},
        {name="Debrief", path="simple/debrief"},
        
        # Completion
        {name="End", path="end"}
    ]

Consent Forms
-------------

When you include ``{name="Consent", path="consent"}`` in your PAGE_LIST, BOFS will display a consent form to participants. You need to create a ``consent.html`` file in your project root directory (next to your ``.toml`` configuration file) that contains your consent text.

.. image:: /examples/quickstart/page_consent.png
  :width: 800
  :alt: The consent page.

**Basic Consent Setup**

.. code-block:: bash

    my_experiment/
    ├── config.toml
    ├── consent.html        # Your consent content
    └── questionnaires/

**Example consent.html**

.. code-block:: html

    <h2>Research Study Consent Form</h2>
    
    <p><strong>Study Title:</strong> Creature Bonding and Strategic Decision-Making Among Pocket Monster Trainers</p>
    <p><strong>Principal Investigator:</strong> Professor Oak, Department of Human-Creature Interaction Studies</p>
    <p><strong>Institution:</strong> Pallet Research Institute, Kanto Regional University</p>
    
    <h3>Purpose of the Study</h3>
    <p>You are invited to participate in a research study examining the psychological factors that 
    influence trainer preferences for different elemental creature types and battle strategies. 
    This study will take approximately 20 minutes to complete.</p>
    
    <h3>What You Will Do</h3>
    <p>If you agree to participate, you will:</p>
    <ul>
        <li>Complete questionnaires about your trainer background and experience</li>
        <li>Rate your preferences for various creature types (fire, water, grass, electric, etc.)</li>
        <li>Make strategic decisions in hypothetical battle scenarios</li>
        <li>Provide feedback about your creature care philosophy</li>
        <li>Answer questions about your regional league participation</li>
    </ul>
    
    <h3>Risks and Benefits</h3>
    <p>There are minimal risks associated with this study, though you may experience mild 
    nostalgia for your early training days or develop strong opinions about creature evolution 
    timing. While there are no direct benefits to you, your participation will contribute to 
    our understanding of trainer psychology and may help improve creature care education programs.</p>
    
    <h3>Confidentiality</h3>
    <p>Your responses will be kept strictly confidential. Your trainer ID number will not be 
    collected, and all data will be stored securely in our research database. No information 
    that could identify you will be shared with regional league officials.</p>
    
    <h3>Voluntary Participation</h3>
    <p>Your participation is completely voluntary. You may withdraw at any time without penalty, 
    and this will not affect your trainer certification status or league standings in any way.</p>
    
    <h3>Contact Information</h3>
    <p>If you have questions about this study, please contact Professor Oak at 
    prof.oak@palletresearch.example or call the Research Institute at (555) PALLET-1. For questions
    about research participant rights, contact the University Ethics Board at ethics@kanto.example.</p>

**How Consent Works**

1. BOFS automatically wraps your consent.html content in a form
2. Participants see radio buttons: "I give my consent" / "I do not give my consent"  
3. Participants must select "I give my consent" to continue
4. If they select "I do not give my consent", they cannot proceed
5. The consent response is automatically recorded in the database

**Consent Without Condition Assignment**

If you want to show consent but not assign experimental conditions, use:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent_nc"},  # No condition assignment
        {name="Survey", path="questionnaire/main"},
        {name="End", path="end"}
    ]

**Advanced Consent Customization**

For more control over consent presentation, you can override the entire consent template by creating ``templates/consent.html`` in your project. See :doc:`../advanced/custom_styling` for template customization details.

Conditional Routing and A/B Testing
------------------------------------

BOFS supports static conditional routing where participants are assigned to an experimental condition at the start, then see different content based on that assignment.

**Setting Up Conditions**

First, define your conditions in the configuration:

.. code-block:: toml

    CONDITIONS = [
        {label="Control", enabled=true},
        {label="High Reward", enabled=true},
        {label="Low Reward", enabled=true}
    ]

- Participants are automatically assigned to the condition with the fewest participants
- Condition numbers start at 1 (Control=1, High Reward=2, Low Reward=3)
- Participants without assigned conditions have condition 0
- Abandoned participants aren't counted when balancing conditions

**Condition Assignment**

Conditions are automatically assigned when participants visit these routes:

- ``/consent`` or ``/consent_nc``
- ``/create_participant`` or ``/create_participant_nc``
- ``/assign_condition``

**Using Conditional Routing in PAGE_LIST**

Show different pages based on participant condition:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        
        # Conditional routing based on assigned condition
        {conditional_routing=[
            {condition=1, page_list=[
                {name="Control Instructions", path="instructions/control"},
                {name="Control Task", path="task/control"}
            ]},
            {condition=2, page_list=[
                {name="High Reward Instructions", path="instructions/high_reward"},
                {name="High Reward Task", path="task/high_reward"}
            ]},
            {condition=3, page_list=[
                {name="Low Reward Instructions", path="instructions/low_reward"},
                {name="Low Reward Task", path="task/low_reward"}
            ]}
        ]},
        
        {name="End", path="end"}
    ]

**Accessing Conditions in Templates**

In custom pages and templates, access the participant's condition:

.. code-block:: html

    {% if session.condition == 1 %}
        <p>You are in the control condition.</p>
    {% elif session.condition == 2 %}
        <p>You are in the high reward condition.</p>
    {% endif %}

**Skipping a page based on prior answers**

Any entry in ``PAGE_LIST`` (including entries inside a ``conditional_routing`` block) can carry a ``show_if`` predicate. When the predicate evaluates to false against the participant's stored questionnaire answers, the page is removed from that participant's flow — ``next_path`` and the breadcrumb skip past it.

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Followup", path="questionnaire/followup", show_if="demographics.age < 18"},
        {name="End", path="end"}
    ]

The expression syntax, the qualified reference forms for repeated-measures designs (``qname.tag.field``), and the behaviour when a referenced questionnaire has not been submitted yet are all described in :doc:`../advanced/expressions`.

Settings for MTurk and Prolific
-------------------------------

Recruiting through MTurk or Prolific brings in a few additional settings — external ID handling, completion codes, return URLs, and session-recovery rules. The full picture is covered in :doc:`../deployment/mturk_prolific`; the settings themselves are described in :doc:`../reference/config_options`.

Multiple Configuration Files
----------------------------

A project can have more than one ``.toml`` file — useful for separating development and production settings, or for keeping a stripped-down ``testing.toml`` that skips straight to the main task. Each file is self-contained (BOFS doesn't merge them); pick the one you want when you launch:

.. code-block:: bash

    BOFS run config.toml -d         # Development
    BOFS run production.toml        # Production
    BOFS run testing.toml -d        # A minimal PAGE_LIST for testing the task

A common split is a ``config.toml`` with the development settings (SQLite, simple admin password, full ``PAGE_LIST``) and a ``production.toml`` that overrides the database URI, admin password, and external-ID settings.

Database
--------

The ``SQLALCHEMY_DATABASE_URI`` setting tells BOFS where to keep its data. SQLite is a good choice for most cases. Use PostgreSQL if you will be collecting data from a large number of concurrent participants.

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = "sqlite:///my_study.db"
    SQLALCHEMY_DATABASE_URI = "postgresql://username:password@host:port/database"

.. warning::
    Adding, removing, or renaming questions in a questionnaire after the database has been created may invalidate the existing schema. During development, delete the ``.db`` file and restart BOFS to recreate it. For live studies with participant data, use the admin panel's "Preview Questionnaire" feature, which can add new columns without touching existing data.

Example Configurations
----------------------

**Simple Survey Study**

.. code-block:: toml

    TITLE = "Personality and Behavior Survey"
    SQLALCHEMY_DATABASE_URI = "sqlite:///personality_survey.db"
    ADMIN_PASSWORD = "admin_password"
    
    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Personality", path="questionnaire/big_five"},
        {name="Behavior Questions", path="questionnaire/behavior"},
        {name="End", path="end"}
    ]

**A/B Testing Experiment**

.. code-block:: toml

    TITLE = "Decision Making Study"
    SQLALCHEMY_DATABASE_URI = "sqlite:///decision_experiment.db"
    ADMIN_PASSWORD = "admin_password"
    
    CONDITIONS = [
        {label="Low Stakes", enabled=true},
        {label="High Stakes", enabled=true}
    ]
    
    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {conditional_routing=[
            {condition=1, page_list=[
                {name="Low Stakes Instructions", path="instructions/low_stakes"}
            ]},
            {condition=2, page_list=[
                {name="High Stakes Instructions", path="instructions/high_stakes"}
            ]}
        ]},
        {name="Decision Task", path="task/decisions"},
        {name="Post-task Questions", path="questionnaire/post_task"},
        {name="End", path="end"}
    ]

For a full MTurk or Prolific configuration, see :doc:`../deployment/mturk_prolific`.

Common Configuration Issues
---------------------------

* **Missing questionnaire files** — every path of the form ``questionnaire/foo`` requires a ``questionnaires/foo.json`` file in the project directory.
* **Template not found** — instruction pages need an ``.html`` file under ``templates/instructions/``; simple pages need one under ``templates/simple/``.
* **Database errors** — check the ``SQLALCHEMY_DATABASE_URI`` syntax and that the user has read/write access to the file or database.
* **PAGE_LIST shape** — the first page must be one of the participant-creation routes (``consent``, ``consent_nc``, ``create_participant``, ``create_participant_nc``); the last page must be ``end``.

Next Steps
----------

* **Create questionnaires** — see :doc:`basic_questionnaires`.
* **Add custom pages** — see :doc:`simple_custom_pages`.
* **See a complete example project** — walk through :doc:`quickstart_existing`.
* **Deploy your study** — see :doc:`../deployment/server_config`.

.. note::
    Restart BOFS whenever you change the configuration file — settings are read at startup.