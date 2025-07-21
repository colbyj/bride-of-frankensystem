MTurk and Prolific Integration
==============================

This guide covers how to configure BOFS experiments for deployment on crowdsourcing platforms like Amazon Mechanical Turk (MTurk) and Prolific. BOFS provides built-in support for external platform integration through configurable external ID handling, completion codes, and session management.

.. note::
    This page focuses on platform integration configuration. For server deployment and hosting setup, see :doc:`server_config`.

Overview of Platform Integration
--------------------------------

BOFS supports crowdsourcing platforms through several key features:

- **External ID Collection**: Automatic capture of participant IDs from URL parameters or dedicated collection pages
- **Session Persistence**: Ability to resume incomplete sessions based on external IDs
- **Completion Codes**: Automatic generation or static completion codes for platform submission
- **Return URLs**: Configurable redirect URLs back to external platforms
- **Quality Control**: Duplicate prevention and session recovery mechanisms

Amazon Mechanical Turk Integration
-----------------------------------

Basic MTurk Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

Add these settings to your TOML configuration file for MTurk integration:

.. code-block:: toml

    # Basic Settings
    TITLE = "Research Study - MTurk"
    SQLALCHEMY_DATABASE_URI = "sqlite:///mturk_study.db"
    SECRET_KEY = "your-unique-secret-key-here"
    ADMIN_PASSWORD = "secure_admin_password"

    # MTurk Integration Settings
    EXTERNAL_ID_LABEL = "MTurk Worker ID"
    EXTERNAL_ID_PROMPT = "Please enter your MTurk Worker ID exactly as it appears in your dashboard."
    
    # Completion Code Configuration
    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy this completion code and paste it into the MTurk HIT to receive payment:"
    
    # Session Management
    RETRIEVE_SESSIONS = true  # Load a user's session via their Worker ID if they try to access the task from the start again
    ALLOW_RETAKES = false     # Prevent a worker from completing the task twice

.. image:: /examples/quickstart/minimal/minimal1.png
  :width: 800
  :alt: The external ID page.

.. image:: /examples/quickstart/minimal/minimal3.png
  :width: 800
  :alt: The end page.

Setting Up MTurk HITs
~~~~~~~~~~~~~~~~~~~~~

When creating your HIT in MTurk, you have two options for participant ID collection:

**Option A: URL Parameter (Recommended)**

Set your HIT URL to automatically pass the Worker ID:

.. code-block:: text

    https://yourdomain.com/consent?external_id=${mturk.workerId}

**Option B: Manual Entry**

Use a simple URL and include the external ID collection page:

.. code-block:: text

    https://yourdomain.com/consent

**Configuration for Both Options**

Add the external ID page to your PAGE_LIST:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Worker ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]

For option A, the input field for the external ID will be automatically populated with the Worker ID.

MTurk Completion Handling
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Generated Completion Codes**

BOFS can generate unique completion codes for each participant:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please copy this completion code and paste it into the MTurk HIT to receive payment:"

**Static Completion Codes**

For studies where all participants use the same code:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    STATIC_COMPLETION_CODE = "BOFS2024"
    COMPLETION_CODE_MESSAGE = "Your completion code is: BOFS2024"

**Return URL Integration**

To redirect participants back to MTurk after completion:

.. code-block:: toml

    # Replace with your actual MTurk submission URL
    OUTGOING_URL = "https://workersandbox.mturk.com/mturk/externalSubmit?assignmentId=ASSIGNMENT_ID_FROM_HIT"

.. note::
    You cannot use both ``GENERATE_COMPLETION_CODE = true`` and ``OUTGOING_URL`` together. Choose one approach based on your HIT setup.

Advanced MTurk Features
~~~~~~~~~~~~~~~~~~~~~~~

**Multiple HITs per Worker**

To allow workers to complete multiple HITs (you usually don't want this for studies or experiments):

.. code-block:: toml

    ALLOW_RETAKES = true
    RETRIEVE_SESSIONS = false

**Session Recovery**

To help workers who accidentally close their browser load their progress:

.. code-block:: toml

    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false

Prolific Integration
--------------------

Basic Prolific Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Prolific has specific requirements for participant ID handling and completion:

.. code-block:: toml

    # Basic Settings
    TITLE = "Research Study - Prolific"
    SQLALCHEMY_DATABASE_URI = "sqlite:///prolific_study.db"
    SECRET_KEY = "your-unique-secret-key-here"
    ADMIN_PASSWORD = "secure_admin_password"

    # Prolific Integration Settings
    EXTERNAL_ID_LABEL = "Prolific ID"
    EXTERNAL_ID_PROMPT = "Your Prolific ID should be automatically detected. If not, please enter it manually."
    
    # Completion Configuration (no code generation for Prolific)
    GENERATE_COMPLETION_CODE = false
    OUTGOING_URL = "https://app.prolific.co/submissions/complete?cc=COMPLETION_CODE"
    
    # Session Management
    RETRIEVE_SESSIONS = true
    ALLOW_RETAKES = false

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Prolific ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]


Setting Up Prolific Studies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In your Prolific study setup, set the study URL to:

.. code-block:: text

    https://yourdomain.com/consent?PROLIFIC_PID={{%PROLIFIC_PID%}}

BOFS automatically captures the ``PROLIFIC_PID`` parameter and stores it as the participant's external ID.

Prolific Completion Requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Prolific requires participants to be redirected to a specific completion URL. Configure it with your study's completion code:

.. code-block:: toml

    OUTGOING_URL = "https://app.prolific.co/submissions/complete?cc=C1ABC123"

Replace ``C1ABC123`` with your actual Prolific completion code found in your study settings.

Custom Completion Pages for Prolific
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you need custom completion handling, you can skip the automatic redirect and customize the end page template:

.. code-block:: toml

    # Don't use OUTGOING_URL for custom completion pages
    GENERATE_COMPLETION_CODE = false

Then customize your ``templates/end.html`` template to show Prolific-specific instructions.


External ID Management In General
---------------------------------

Understanding External ID Collection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BOFS can collect external IDs (participant identifiers from external platforms) in two ways:

**1. URL Parameters (Automatic)**

BOFS automatically processes these URL parameters:

- ``external_id``: Generic external platform ID
- ``PROLIFIC_PID``: Prolific participant ID  
- ``mTurkID``: MTurk Worker ID (for backward compatibility)

**2. Manual Entry**

Include the ``external_id`` page in your PAGE_LIST to prompt participants:

.. code-block:: toml

    PAGE_LIST = [
        {name="Consent", path="consent"},
        {name="Participant ID", path="external_id"},
        {name="Study", path="questionnaire/main"},
        {name="End", path="end"}
    ]

Customizing External ID Collection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Configure the external ID collection interface:

.. code-block:: toml

    EXTERNAL_ID_LABEL = "Your Platform Participant ID"
    EXTERNAL_ID_PROMPT = "Please enter the participant ID provided by the research platform."

Session Management Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Control how BOFS handles returning participants:

.. code-block:: toml

    # Allow participants to resume incomplete sessions
    RETRIEVE_SESSIONS = true
    
    # Prevent duplicate participation (default)
    ALLOW_RETAKES = false
    
    # Allow multiple participations from same ID
    ALLOW_RETAKES = true

When ``RETRIEVE_SESSIONS = true``, BOFS will:

1. Check if an external ID has been used before
2. Load the previous session if incomplete
3. Resume from the last completed page
4. Preserve condition assignments

Completion Code Strategies
--------------------------

Generated Completion Codes
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For unique codes per participant:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = true
    COMPLETION_CODE_MESSAGE = "Please enter this code to complete the study:"

BOFS creates UUID-based unique codes automatically.

Static Completion Codes
~~~~~~~~~~~~~~~~~~~~~~~

For the same code across all participants:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    STATIC_COMPLETION_CODE = "STUDY2024"
    COMPLETION_CODE_MESSAGE = "Your completion code is: STUDY2024"

Redirect-Only Completion
~~~~~~~~~~~~~~~~~~~~~~~~

To skip completion codes and redirect immediately:

.. code-block:: toml

    GENERATE_COMPLETION_CODE = false
    OUTGOING_URL = "https://external-platform.com/complete"



Troubleshooting Common Issues
-----------------------------

Debug Mode for Troubleshooting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run BOFS in debug mode for detailed error information:

.. code-block:: bash

    BOFS config.toml -d

Debug mode provides:

- Detailed error messages in the browser
- Console logging of configuration issues  
- Step-by-step request processing information
- Database query logging

Admin Panel Monitoring
~~~~~~~~~~~~~~~~~~~~~~

Use the admin panel to monitor external platform integration:

1. Navigate to ``/admin`` with your admin password
2. View the **Participants** table to check external ID storage
3. Check the **Progress** table for session flow tracking
4. Monitor **Results** for questionnaire response collection

Security Considerations
-----------------------

External ID Privacy
~~~~~~~~~~~~~~~~~~~

- External IDs are stored in the database along with responses
- Consider anonymization requirements for your research
- MTurk Worker IDs and Prolific IDs are considered personal identifiers
- Follow your institution's IRB guidelines for external ID handling

Configuration Security
~~~~~~~~~~~~~~~~~~~~~~

Always use strong, unique secret keys:

.. code-block:: toml

    SECRET_KEY = "generated-secret-key-here-not-simple-text"

Generate secure keys using:

.. code-block:: python

    import secrets
    print(secrets.token_hex(32))

.. warning::
    Never commit secret keys to public version control or share them publicly.

Best Practices
--------------

**Pre-Deployment**

1. **Always test integration** with a small pilot study before full deployment
3. **Test session recovery** scenarios thoroughly with realistic interruptions
4. **Document your specific configuration** for future reference and replication

**During Data Collection**

1. **Monitor the admin panel** regularly during active data collection
2. **Keep completion instructions clear** and platform-specific
3. **Watch for duplicate external IDs** that might indicate configuration issues
4. **Backup your database** regularly during active studies
5. **Collect data in small batches** to avoid overloading the server

**Platform-Specific Guidelines**

- **MTurk**: Use qualification requirements to pre-screen participants when possible
- **Prolific**: Take advantage of Prolific's built-in screening and demographic filters  
- **Both**: Clearly communicate completion requirements in your study description

**Quality Control**

1. Consider adding attention checks to your questionnaires
2. Monitor participant completion times in the admin panel
3. Use the ``ABANDONED_MINUTES`` setting to identify incomplete sessions and ensure participants are balanced between conditions

Next Steps
----------

After configuring your platform integration:

- **Deploy your experiment to a server**: See :doc:`server_config` for production deployment guidance
- **Monitor data collection**: Use the admin panel to track participant progress
- **Export your data**: Use the built-in CSV export functionality for analysis

.. note::
    Remember that changes to questionnaires after data collection begins may require database management. Always test configuration changes on a separate instance of the database first.
