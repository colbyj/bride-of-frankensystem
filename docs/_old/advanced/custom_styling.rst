Customizing BOFS's Appearance
=============================

BOFS pages are built from HTML templates and a ``style.css``, both of which you can override per project. Anything you place under your project's ``templates/`` or ``static/`` directories takes precedence over the BOFS defaults.

Template lookup order:

1. Your project's ``templates/`` (highest priority)
2. Blueprint ``templates/`` directories
3. BOFS default templates (lowest priority)

The BOFS default ``static/`` directory contains ``style.css`` (main stylesheet, defined with CSS custom properties), ``bootstrap.min.css``, ``style_admin.css``, and the bundled JavaScript libraries (jQuery, Bootstrap, HTMX).

Quick Start: Override the Stylesheet
------------------------------------

The simplest customization is to drop your own ``style.css`` into the project's ``static/`` directory. Copying the default as a starting point keeps everything that already works:

.. code-block:: bash

    cp /path/to/BOFS/static/style.css ./static/style.css

Edit ``./static/style.css`` and restart BOFS (``BOFS run config.toml -d``). Your version takes over from the default.

Quick: Header Color from Config
-------------------------------

If the only thing you want to change is the color of the title bar, you can set ``HEADER_COLOR`` in your project's ``.toml`` config — no custom ``style.css`` required:

.. code-block:: toml

    HEADER_COLOR = "#003366"   # any CSS color: hex, name, rgb(), rgba(), hsl(), hsla()

For broader customization (fonts, layout, multiple colors), continue with the CSS-based approach below.

Customizing Colors and Fonts
-----------------------------

BOFS uses CSS custom properties (variables) that make it easy to customize colors, fonts, and layout:

**Key CSS Variables**

.. code-block:: css

    :root {
        /* Layout */
        --contents-width: 967px;           /* Main content width */
        
        /* Colors */
        --top-bar-color: #8CB737;          /* Header bar color */
        --bs-border-color: black;          /* Border color */
        
        /* Typography */
        --font-size-main: 12pt;            /* Body text size */
        --font-size-h1: 18pt;              /* Main heading size */
        --font-size-h2: 16pt;              /* Subheading size */
        --font-size-h3: 13pt;              /* Section heading size */
        --question-title-font-size: 13pt;  /* Question title size */
        --question-instructions-font-size: 11pt; /* Question instruction size */
    }

**Example: University Branding**

Create ``static/style.css`` with your institution's colors:

.. code-block:: css

    /* Import the default BOFS styles */
    @import url('/BOFS_static/style.css');
    
    /* Override with university colors */
    :root {
        --top-bar-color: #003366;          /* Hypothetical University blue */
        --font-size-main: 14pt;            /* Larger text */
    }
    
    body {
        font-family: 'Georgia', serif;     /* Hypothetical University font */
        background-color: #f8f9fa;         /* Light background */
    }
    
    .content {
        max-width: 800px;                  /* Narrower content */
        margin: 0 auto;                    /* Center content */
        background: white;                 /* White content area */
        padding: 2rem;                     /* More padding */
        box-shadow: 0 2px 10px rgba(0,0,0,0.1); /* Subtle shadow */
    }


Template Customization
----------------------

**Available Templates to Override**

BOFS includes these templates you can customize:

.. code-block:: text

    templates/
    ├── template.html              # Base template (header, navigation)
    ├── consent.html               # Consent form page
    ├── external_id.html           # External ID collection
    ├── questionnaire.html         # Main questionnaire template
    ├── questionnaire_macro.html   # Questionnaire rendering macros
    ├── instructions.html          # Instruction pages
    ├── simple.html                # Simple content pages
    ├── end.html                   # Study completion page
    ├── unity_webgl.html           # Unity WebGL integration
    └── questions/                 # Individual question types
        ├── radiolist.html
        ├── checklist.html
        ├── slider.html
        ├── field.html
        └── ...


.. warning::
    Making customizations may make your project incompatible with future versions of BOFS. Make note of the specific changes you make to the templates or styles so you can reproduce them on the newest release.


**Customizing the Base Template**

Copy and modify the base template to change the overall layout:

.. code-block:: bash

    # Copy base template to your project
    mkdir -p templates
    cp /path/to/BOFS/templates/template.html templates/

Key sections in ``template.html``:

.. code-block:: html

    <!DOCTYPE html>
    <html>
    <head>
        <title>{% block title %}{{ config['TITLE'] }}{% endblock %}</title>
        <!-- CSS includes -->
        <link rel="stylesheet" href="{{ url_for('BOFS_static', filename='style.css') }}">
        {% block head %}{% endblock %}
    </head>
    <body>
        <!-- Your custom header -->
        <div class="header">
            <h1>{{ config['TITLE'] }}</h1>
        </div>
        
        <!-- Main content area -->
        <div class="content">
            {% block content %}{% endblock %}
        </div>
        
        <!-- Your custom footer -->
        {% block scripts %}{% endblock %}
    </body>
    </html>

**Example: Custom Header and Footer**

.. code-block:: html

    <!-- templates/template.html -->
    {% from "macros.html" import btnContinue, adminControls, checkUserActive %}
    <!DOCTYPE html>
    <html>
    <head>
        <title>University Research Study</title>
        <link rel="stylesheet" href="{{ url_for('BOFS_static', filename='bootstrap.min.css') }}">
        <link rel="stylesheet" href="{{ style_url }}">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" integrity="sha512-SnH5WK+bZxgPHs44uWIX+LLJAJ9/2PkPKZ5QiAj6Ta86w+fsb2TkcmfRyVX3pBnMFcV7oQPJkl9QevSCWr3W6A==" crossorigin="anonymous" referrerpolicy="no-referrer" />
        <style>
            .university-header {
                background: #003366;
                color: white;
                padding: 1rem;
                text-align: center;
            }
            .university-footer {
                background: #f8f9fa;
                padding: 1rem;
                text-align: center;
                margin-top: 2rem;
                border-top: 1px solid #dee2e6;
            }
        </style>
        <script src="{{ url_for('BOFS_static', filename='js/jquery-3.7.1.min.js') }}"></script>
        <script src="{{ url_for('BOFS_static', filename='js/bootstrap.bundle.min.js') }}"></script>
        <script src="{{ url_for('BOFS_static', filename='js/htmx.min.js') }}"></script>
        <script src="{{ url_for('BOFS_static', filename='js/json-enc.js') }}"></script>

        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {% block head %}{% endblock %}
    </head>
    <body>
        <!-- Custom header -->
        <div class="university-header">
            <h2>Psychology Department Research Study</h2>
            <p>University of Example</p>
        </div>

        <!-- Main content -->
        <div class="content">
            {% block top %}{% endblock %}
            {% block content %}{% endblock %}
            {% block bottom %}{% endblock %}
        </div>

        <!-- Custom footer -->
        <div class="university-footer">
            <p>Questions? Contact research@university.edu</p>
            <p>IRB Protocol #2024-001</p>
        </div>

        {{ adminControls() }}
        {{ checkUserActive() }}
    </body>
    </html>


Question Type Customization
---------------------------

**Customizing Question Appearance**

Override individual question type templates:

.. code-block:: html

    <!-- templates/questions/radiolist.html -->
    <div class="question-container">
        <h3 class="question-title">{{ question.text }}</h3>
        
        {% if question.subText %}
        <div class="question-instructions">{{ question.subText|safe }}</div>
        {% endif %}
        
        <div class="custom-radio-group">
            {% for option in question.options %}
            <div class="custom-radio-option">
                <input type="radio" 
                       name="{{ question.id }}" 
                       value="{{ loop.index0 }}" 
                       id="{{ question.id }}_{{ loop.index0 }}"
                       class="custom-radio">
                <label for="{{ question.id }}_{{ loop.index0 }}" class="custom-radio-label">
                    {{ option }}
                </label>
            </div>
            {% endfor %}
        </div>
    </div>

Adding Custom Assets
--------------------

Anything you place under ``static/`` is served at ``/static/<path>`` — images, JavaScript, custom fonts, and so on. Reference them from your templates the same way you would in any HTML page:

.. code-block:: html

    <link href="/static/fonts/UniversityFont.woff2" rel="preload" as="font" type="font/woff2" crossorigin>
    <img src="/static/university-logo.png" alt="University Logo">
    <script src="/static/custom.js"></script>

For custom fonts, declare the ``@font-face`` in your ``style.css`` and apply it to ``body`` (or wherever you want it):

.. code-block:: css

    @font-face {
        font-family: 'UniversityFont';
        src: url('/static/fonts/UniversityFont.woff2') format('woff2');
        font-weight: normal;
        font-style: normal;
    }

    body {
        font-family: 'UniversityFont', 'Segoe UI', Arial, sans-serif;
    }

