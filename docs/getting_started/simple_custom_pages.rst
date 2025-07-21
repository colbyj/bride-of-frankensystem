Simple Custom Pages
===================

BOFS provides several ways to create custom pages beyond questionnaires. This section covers simple approaches that don't require programming - perfect for instruction pages, consent forms, and informational content.

Instruction Pages
-----------------

Instruction pages are the most common way to display static content. They automatically include a "Continue" button and use your experiment's theme.

**Creating Instruction Pages**

1. Create an HTML file in your project's ``templates/instructions/`` directory
2. Add the page to your ``PAGE_LIST`` configuration

**Example: Creating a Welcome Page**

Create ``templates/instructions/welcome.html``:

.. code-block:: html

    <h2>Welcome to Our Study</h2>
    
    <p>Thank you for participating in our research study. This experiment will take approximately 15 minutes to complete.</p>
    
    <p>During this study, you will:</p>
    <ul>
        <li>Answer some demographic questions</li>
        <li>Complete a short task</li>
        <li>Provide feedback about your experience</li>
    </ul>
    
    <p><strong>Important:</strong> Please complete this study in one sitting without taking breaks.</p>

Then add it to your configuration:

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='Welcome', path='instructions/welcome'},
        {name='Demographics', path='questionnaire/demographics'},
        {name='End', path='end'}
    ]

**Built-in Variables**

Instruction pages are Jinja2 templates, so you can use variables and logic:

.. code-block:: html

    <h2>Instructions for {{ session['condition'] }} Condition</h2>
    
    {% if session['condition'] == 'treatment' %}
        <p>You have been assigned to the treatment group.</p>
    {% else %}
        <p>You have been assigned to the control group.</p>
    {% endif %}
    
    <p>Your participant ID is: {{ session['participant_id'] }}</p>

Simple HTML Pages
-----------------

For more control over navigation, use simple HTML pages. These don't include an automatic "Continue" button, so you control exactly how participants move through your study.

**Creating Simple Pages**

1. Create an HTML file in your project's ``templates/simple/`` directory
2. Add the page to your ``PAGE_LIST`` with the ``simple/`` prefix
3. Include your own navigation elements

**Example: Custom Navigation**

Create ``templates/simple/custom_instructions.html``:

.. code-block:: html

    <h2>Task Instructions</h2>
    
    <p>Read these instructions carefully before proceeding.</p>
    
    <div id="instructions-content" style="display: none;">
        <p>Detailed instructions will appear here after 10 seconds...</p>
        <button onclick="location.href='/redirect_next_page'">I'm Ready to Begin</button>
    </div>
    
    <script>
    setTimeout(function() {
        document.getElementById('instructions-content').style.display = 'block';
    }, 10000);  // Show after 10 seconds
    </script>

Add to configuration:

.. code-block:: toml

    PAGE_LIST = [
        {name='Instructions', path='simple/custom_instructions'},
        {name='Task', path='task'},
        {name='End', path='end'}
    ]

**Navigation Options**

For simple pages, you can redirect participants using:
- ``/redirect_next_page`` - Go to the next page in PAGE_LIST
- ``/redirect_to/page_name`` - Go to a specific page
- JavaScript: ``location.href = '/redirect_next_page'``

Serving Static Files
--------------------

BOFS automatically serves files from your project's ``static/`` directory at the ``/static`` URL path. This is perfect for images, videos, audio files, and other media.

**File Organization**

.. code-block:: text

    your_project/
    ├── static/
    │   ├── images/
    │   │   ├── stimulus1.jpg
    │   │   └── logo.png
    │   ├── videos/
    │   │   └── intro.mp4
    │   └── audio/
    │       └── instructions.mp3
    └── templates/
        └── instructions/
            └── media_example.html

**Using Static Files in Templates**

Reference static files using the ``/static`` URL path:

.. code-block:: html

    <h2>Study Materials</h2>
    
    <img src="/static/images/logo.png" alt="Lab Logo" width="200">
    
    <p>Please watch this brief introduction video:</p>
    <video controls width="400">
        <source src="/static/videos/intro.mp4" type="video/mp4">
        Your browser doesn't support video playback.
    </video>
    
    <p>Click to hear the audio instructions:</p>
    <audio controls>
        <source src="/static/audio/instructions.mp3" type="audio/mpeg">
        Your browser doesn't support audio playback.
    </audio>

**Supported File Types**

Common file types that work well:

- **Images**: ``.jpg``, ``.png``, ``.gif``, ``.svg``
- **Videos**: ``.mp4``, ``.webm``, ``.ogg``
- **Audio**: ``.mp3``, ``.wav``, ``.ogg``
- **Documents**: ``.pdf`` (opens in browser)
- **Data**: ``.json``, ``.csv``, ``.txt``

Dynamic Content with Jinja2
---------------------------

Both instruction and simple pages support Jinja2 templating for dynamic content. BOFS automatically provides several useful variables in all templates:

**Available Template Variables**

==================== ===================================
Variable             Description  
==================== ===================================
``session``          Flask session containing participant data
``participant``      Current participant object (if logged in)
``debug``            Boolean indicating debug mode
``config``           BOFS configuration settings from TOML file
``flat_page_list``   List of all pages in the experiment
==================== ===================================

**Session Variables**

The ``session`` object contains key participant information:

.. code-block:: html

    <!-- Core session data -->
    <p>Participant ID: {{ session.participantID }}</p>
    <p>Condition: {{ session.condition }}</p>
    <p>Current page: {{ session.currentUrl }}</p>
    
    <!-- Optional session data (if configured) -->
    {% if session.mTurkID %}
        <p>External ID: {{ session.mTurkID }}</p>
    {% endif %}
    
    {% if session.code %}
        <p>Completion code: {{ session.code }}</p>
    {% endif %}

**Configuration Access**

Access any setting from your TOML configuration file:

.. code-block:: html

    <!-- Basic config access -->
    <h1>{{ config.TITLE }}</h1>
    
    <!-- Use config in conditional logic -->
    {% if config.REQUIRE_EXTERNAL_ID %}
        <p>External ID required for this study</p>
    {% endif %}
    
    <!-- Custom config variables -->
    <p>Study duration: {{ config.EXPECTED_DURATION }} minutes</p>

**Debug Mode Detection**

Show different content in development vs. production:

.. code-block:: html

    {% if debug %}
        <div style="background: yellow; padding: 10px;">
            <strong>DEBUG MODE:</strong> This is a test run
        </div>
    {% endif %}

.. note::
    Accessing ``session['condition']`` is particularly useful for showing different instructions or content based on experimental conditions.


**Conditional Content by Condition**

.. code-block:: html

    {% if session['condition'] == 'high_stakes' %}
        <p style="color: red; font-weight: bold;">
            IMPORTANT: Your performance on this task will affect your payment.
        </p>
    {% else %}
        <p>Complete this task to the best of your ability.</p>
    {% endif %}

**Displaying Previous Responses**

.. code-block:: html

    <h2>Please Confirm Your Information</h2>
    
    <p>You previously told us:</p>
    <ul>
        <li>Age: {{ participant.questionnaire("demographics").age }}</li>
        <li>Gender: {{ participant.questionnaire("demographics").gender }}</li>
    </ul>
    
    <p>Is this information correct?</p>

.. note::
    For comprehensive examples of accessing participant data, questionnaire responses, and custom table data, see :doc:`../reference/accessing_participant_data`.


**Using Loop Variables**

.. code-block:: html

    <h2>Study Overview</h2>
    
    <p>This study consists of {{ config.TOTAL_ROUNDS }} rounds.</p>
    
    {% for round_num in range(1, config.TOTAL_ROUNDS + 1) %}
        <p>Round {{ round_num }}: {{ config.ROUND_DESCRIPTIONS[round_num-1] }}</p>
    {% endfor %}

Best Practices
--------------

**When to Use Each Type**

- **Instruction Pages**: For standard informational content with simple navigation
- **Simple Pages**: When you need custom navigation, timing controls, or interactive elements
- **Static Files**: For media content (images, videos, audio) and downloadable files

**Content Guidelines**

- Keep text concise and scannable
- Use headings to organize information
- Include progress indicators for long studies
- Test content with your target population
- Ensure accessibility (alt text for images, captions for videos)

**File Organization**

.. code-block:: text

    your_project/
    ├── static/
    │   ├── css/           # Custom stylesheets
    │   ├── js/            # Custom JavaScript
    │   ├── images/        # Study images
    │   └── media/         # Videos, audio
    ├── templates/
    │   ├── instructions/  # Standard instruction pages
    │   └── simple/        # Custom navigation pages
    └── config.toml

**Performance Tips**

- Optimize images for web (use appropriate formats and sizes)
- Consider file sizes for participants with slow connections
- Use progressive loading for large media files
- Test media playback across different browsers and devices

Next Steps
----------

- For interactive pages that require programming, see :doc:`../advanced/advanced_custom_pages`
- For integrating with external tasks, see :doc:`../examples/integrating_js_task`
- For complete examples, see :doc:`../examples/ab_experiment`