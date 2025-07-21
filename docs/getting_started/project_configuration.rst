Configuring Your Experiment
===========================

Every BOFS experiment is defined by a TOML configuration file that describes how your study works. This configuration controls everything from the sequence of pages participants see to how they're assigned to experimental conditions.

.. note::
    For a complete reference of all configuration options, see :doc:`../reference/config_options`.

Understanding TOML Configuration Files
---------------------------------------

BOFS uses TOML (Tom's Obvious, Minimal Language) files to configure experiments. TOML is designed to be easy to read and write, using a simple key-value format:

.. code-block:: toml

    # This is a simple key-value pair
    TITLE = "My Research Study"

    # Any line starting with "#" is a comment and not parsed
    
    # This is a list
    CONDITIONS = [
        {label="Control", enabled=true},
        {label="Treatment", enabled=true}
    ]

**Key Benefits of TOML:**
- Human-readable and easy to edit
- Supports comments for documentation
- Clear data types (strings, numbers, booleans, lists)
- No complex syntax to learn

Basic Configuration Structure
-----------------------------

Every BOFS project needs a configuration file (typically named ``config.toml``) with these essential settings:

.. code-block:: toml

    # Basic project information
    TITLE = "My Research Study"
    SECRET_KEY = "your-unique-secret-key-here"
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
**SECRET_KEY**              Random string for session security (see below)
**PORT**                    The port that your experiment will run on (e.g., the "5000" in http://localhost:5000)
**SQLALCHEMY_DATABASE_URI** Database connection (use SQLite for development)
**ADMIN_PASSWORD**          Password for accessing admin panel at ``/admin``
**PAGE_LIST**               The sequence of pages that participants will encounter
=========================== =======================================================

**Generating a Secret Key**

Your secret key should be a random string unique to your project. You can generate one by typing random characters on your keyboard, or via Python:

.. code-block:: python

    import secrets
    print(secrets.token_hex(16))
    # Example output: "a1b2c3d4e5f6789012345678abcdef90"

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

.. image:: /examples/quickstart/minimal/minimal0.png
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

.. note::
    For a complete working example of A/B testing, see :doc:`../examples/ab_experiment`.

Settings for MTurk and Prolific Deployment
-------------------------------------------

When deploying to crowdsourcing platforms, additional configuration options become important:

.. code-block:: toml

    # External ID management
    EXTERNAL_ID_LABEL = "MTurk Worker ID"
    EXTERNAL_ID_PROMPT = "Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."
    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false
    
    # Completion codes
    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy and paste this code into the MTurk form:"
    
    # Session management
    ABANDONED_MINUTES = 30
    COUNTS_INCLUDE_ABANDONED = false

============================== =======================================================
Setting                        Description
============================== =======================================================
**EXTERNAL_ID_LABEL**          Label for external ID field (e.g., "MTurk Worker ID")
**EXTERNAL_ID_PROMPT**         Instructions for external ID entry
**RETRIEVE_SESSIONS**          Allow participants to resume if they return with same ID
**ALLOW_RETAKES**              If false, reject duplicate external IDs
**GENERATE_COMPLETION_CODE**   Create random completion codes
**COMPLETION_CODE_MESSAGE**    Instructions for using completion code
**ABANDONED_MINUTES**          Minutes before participant considered abandoned
**COUNTS_INCLUDE_ABANDONED**   Include abandoned participants in condition balancing
============================== =======================================================

For complete deployment guidance, see :doc:`../deployment/mturk_prolific`.

Multiple Configuration Files Strategy
--------------------------------------

For complex projects, you might use multiple configuration files for different purposes:

**Development vs. Production**

``config.toml`` (base configuration):

.. code-block:: toml

    TITLE = "My Study"
    SECRET_KEY = "development-secret-key"
    ADMIN_PASSWORD = "admin123"
    SQLALCHEMY_DATABASE_URI = "sqlite:///study.db"
    
    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Main Task", path="task/experiment"},
        {name="End", path="end"}
    ]

``production.toml`` (production overrides):

.. code-block:: toml

    SECRET_KEY = "production-secret-key-very-long-and-random"
    ADMIN_PASSWORD = "secure_production_password"
    SQLALCHEMY_DATABASE_URI = "postgresql://user:pass@host/database"
    
    # Production-specific settings
    GENERATE_COMPLETION_CODE = true
    EXTERNAL_ID_LABEL = "Prolific ID"

**Testing Different Flows**

``testing.toml`` (minimal flow for testing):

.. code-block:: toml

    # Minimal flow for testing just the main task
    PAGE_LIST = [
        {name="Create Participant", path="create_participant"},
        {name="Main Task", path="task/experiment"},
        {name="End", path="end"}
    ]

``full_study.toml`` (complete experiment):

.. code-block:: toml

    # Full experimental flow with all questionnaires
    PAGE_LIST = [
        {name="External ID", path="external_id"},
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Pre-task Survey", path="questionnaire/pre_task"},
        {name="Instructions", path="instructions/task_intro"},
        {name="Practice", path="task/practice"},
        {name="Main Task", path="task/experiment"},
        {name="Post-task Survey", path="questionnaire/post_task"},
        {name="Debrief", path="questionnaire/debrief"},
        {name="End", path="end"}
    ]

**Using Different Configurations**

.. code-block:: bash

    # Development
    BOFS config.toml -d
    
    # Production
    BOFS production.toml
    
    # Testing just the main task
    BOFS testing.toml -d

Database and Data Considerations
---------------------------------

**Database Changes Warning**

.. warning::
    If you change a questionnaire in any way (adding/removing questions, changing question IDs), your existing database may become invalid. During development, simply delete your ``.db`` file and restart BOFS. For live studies with participant data, use the admin panel's questionnaire preview feature to safely add new database columns.

**Essential Settings**

=========================== =======================================================
Setting                     Description
=========================== =======================================================
**PORT**                    Port for local development (default: 5000)
**SQLALCHEMY_DATABASE_URI** Database connection string
=========================== =======================================================

**Database Examples**

.. code-block:: toml

    # Development (SQLite)
    SQLALCHEMY_DATABASE_URI = "sqlite:///my_study.db"
    
    # Production (PostgreSQL)  
    SQLALCHEMY_DATABASE_URI = "postgresql://username:password@host:port/database"

Example Configurations
----------------------

**Simple Survey Study**

.. code-block:: toml

    TITLE = "Personality and Behavior Survey"
    SECRET_KEY = "survey-secret-key-here"
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
    SECRET_KEY = "experiment-secret-key-here"
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

**MTurk Study**

.. code-block:: toml

    TITLE = "Cognitive Task Study"
    SECRET_KEY = "mturk-study-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///mturk_study.db"
    ADMIN_PASSWORD = "admin_password"
    
    # MTurk-specific settings
    EXTERNAL_ID_LABEL = "MTurk Worker ID"
    EXTERNAL_ID_PROMPT = "Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."
    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy and paste this code into the MTurk form:"
    ALLOW_RETAKES = false
    
    PAGE_LIST = [
        {name="External ID", path="external_id"},
        {name="Consent", path="consent"},
        {name="Demographics", path="questionnaire/demographics"},
        {name="Task Instructions", path="instructions/task_intro"},
        {name="Cognitive Task", path="task/cognitive"},
        {name="Post-task Survey", path="questionnaire/post_task"},
        {name="End", path="end"}
    ]

Validation and Testing
----------------------

**Test Your Configuration**

1. **Syntax Check**: Start your project with ``BOFS config.toml -d``
2. **Participant Flow**: Visit ``http://localhost:5000`` to test the complete participant experience
3. **Admin Access**: Visit ``http://localhost:5000/admin`` to test admin panel access
4. **Error Checking**: Watch the console for configuration errors or warnings

**Common Configuration Issues**

- **Missing questionnaire files**: Ensure ``.json`` files exist in ``questionnaires/`` directory
- **Template not found**: Check that instruction and simple page templates exist in correct directories
- **Database errors**: Verify database URI format and file permissions
- **Invalid secret key**: Use a proper random secret key, not a simple string like "abc123"
- **PAGE_LIST errors**: Ensure first page is a participant creation route and last page is "end"

**Configuration Best Practices**

- Use descriptive names in PAGE_LIST for easier admin panel navigation
- Keep development and production configurations separate
- Document your experimental design with comments in the TOML file
- Test with multiple participants to verify condition assignment works correctly
- Backup your configuration files along with your questionnaire and template files

Next Steps
----------

Now that you understand BOFS configuration:

- **Create questionnaires**: See :doc:`basic_questionnaires` to learn about defining survey questions
- **Add custom pages**: See :doc:`simple_custom_pages` for instruction pages and custom content
- **See complete examples**: Explore :doc:`../examples/ab_experiment` and :doc:`../examples/quickstart`
- **Deploy your study**: When ready for participants, see :doc:`../deployment/server_config`

.. note::
    Remember to restart your BOFS application whenever you modify the configuration file to ensure changes take effect.