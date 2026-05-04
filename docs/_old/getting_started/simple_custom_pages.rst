Simple Custom Pages
===================

BOFS supports three kinds of custom pages that don't require any Python — *instruction pages*, which display static HTML with an automatic "Continue" button; *simple pages*, which give you control over the page content while still inheriting the project's styling and chrome; and *custom pages*, which render the entire HTML document with no BOFS wrapping at all. All three are written as HTML templates inside your project directory.

Instruction Pages
-----------------

Instruction pages display static content with a "Continue" button at the bottom that advances to the next page in ``PAGE_LIST``.

To create one: drop an HTML file into ``templates/instructions/`` and reference it in ``PAGE_LIST`` as ``instructions/<filename>``.

For example, ``templates/instructions/welcome.html``:

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

Instruction pages are `Jinja2 <https://jinja.palletsprojects.com/en/stable/templates/>`__ templates, so you can use variables and logic:

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

Simple pages are like instruction pages but without the automatic "Continue" button — useful when you want to gate progress (a timer, a quiz the participant has to pass, a JavaScript task that decides when it's done). Drop an HTML file into ``templates/simple/`` and reference it in ``PAGE_LIST`` as ``simple/<filename>``.

For example, ``templates/simple/custom_instructions.html``:

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

Custom HTML Pages
-----------------

Custom pages are like simple pages but with no BOFS template wrapping at all — no header, no breadcrumbs, no project styling. The template you provide is rendered as the entire HTML document. Use these when a task needs full control over the page (for example, a jsPsych or lab.js experiment that takes over the viewport, or any task where the BOFS chrome would interfere). Drop an HTML file into ``templates/custom/`` and reference it in ``PAGE_LIST`` as ``custom/<filename>``.

For example, ``templates/custom/my_task.html``:

.. code-block:: html

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>My Task</title>
    </head>
    <body>
        <main></main>
        <script src="/static/my_task.js"></script>
    </body>
    </html>

Add to configuration:

.. code-block:: toml

    PAGE_LIST = [
        {name='Task', path='custom/my_task'},
        {name='End', path='end'}
    ]

Custom pages are still Jinja2 templates and have access to the same template variables (``session``, ``participant``, ``config``, ``debug``) as instruction and simple pages. The same redirect routes apply: ``/redirect_next_page``, ``/redirect_to/<page_name>``, or POST to the page route.

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

Both instruction and simple pages support `Jinja2 <https://jinja.palletsprojects.com/en/stable/templates/>`__  templating for dynamic content. BOFS automatically provides several useful variables in all templates:

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
    For comprehensive examples of accessing participant data, questionnaire responses, and custom table data, see :doc:`../advanced/accessing_participant_data`.


**Using Loop Variables**

.. code-block:: html

    <h2>Study Overview</h2>
    
    <p>This study consists of {{ config.TOTAL_ROUNDS }} rounds.</p>
    
    {% for round_num in range(1, config.TOTAL_ROUNDS + 1) %}
        <p>Round {{ round_num }}: {{ config.ROUND_DESCRIPTIONS[round_num-1] }}</p>
    {% endfor %}

Choosing Between Them
---------------------

* **Instruction page** — static content with the standard Continue button. The default for any informational page.
* **Simple page** — content rendered inside the BOFS template (header, breadcrumbs, project styling). Use when you need custom navigation, a timer, or an interactive element to gate progress, but want the page to look like the rest of the experiment.
* **Custom page** — the template is the entire HTML document, with no BOFS chrome. Use when a task needs full viewport control or its own ``<head>``/``<body>`` (e.g., jsPsych or lab.js).
* **Static file** — for media (images, videos, audio) and downloadable files. Reference it from any of the page types above using ``/static/<path>``.

Next Steps
----------

- For interactive pages that require programming, see :doc:`../advanced/advanced_custom_pages`
- For integrating with external tasks, see :doc:`tutorial_js_task`
- For complete examples, see :doc:`../examples/example_projects`