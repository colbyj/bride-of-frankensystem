Customizing BOFS's Appearance
=============================

BOFS provides flexible customization options that allow you to modify the visual appearance of your experiments without changing the core BOFS code. You can override templates, customize CSS styles, and add your own branding to create a unique look for your studies.

.. note::
    BOFS uses a template file override system. Any file you place in your project's ``templates/`` directory will take precedence over the default BOFS files.

    BOFS will also check for the presence of a ``style.css`` inside of your project's ``static/`` directory, which will take precedence over the default ``style.css``.

Overview of BOFS's Styling System
---------------------------------

**Template Override System**

BOFS searches for templates in this order:

1. **Your project's templates/** directory (highest priority)
2. **Blueprint templates/** directories  
3. **BOFS default templates/** (lowest priority)

**Static File System**

BOFS includes these key static files:

- ``style.css`` - Main stylesheet with CSS custom properties
- ``bootstrap.min.css`` - Bootstrap framework
- ``style_admin.css`` - Admin panel styling
- JavaScript libraries (jQuery, Bootstrap, HTMX)

Quick Start: Basic Customization
---------------------------------

**1. Create Your Project Structure**

.. code-block:: bash

    my_experiment/
    ├── config.toml
    ├── templates/           # Your custom templates (optional)
    ├── static/             # Your custom styles (optional)
    │   └── style.css
    └── questionnaires/
        └── main.json

**2. Copy and Modify Default Styles**

.. code-block:: bash

    # Copy BOFS default stylesheet to your project
    cp /path/to/BOFS/static/style.css ./static/style.css
    
    # Now edit ./static/style.css to customize appearance

**3. Test Your Changes**

.. code-block:: bash

    BOFS config.toml -d

Your custom ``style.css`` will automatically override the default BOFS stylesheet.

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

**Project Structure with Assets**

.. code-block:: text

    my_experiment/
    ├── static/
    │   ├── style.css           # Custom styles
    │   ├── university-logo.png # Logo image
    │   ├── custom.js           # Custom JavaScript
    │   └── fonts/              # Custom fonts
    │       └── UniversityFont.woff2
    ├── templates/
    │   └── template.html       # Custom base template
    └── config.toml

**Using Custom Assets**

.. code-block:: html

    <!-- In your templates -->
    <link href="/static/fonts/UniversityFont.woff2" rel="preload" as="font" type="font/woff2" crossorigin>
    <img src="/static/university-logo.png" alt="University Logo">
    <script src="/static/custom.js"></script>

**Custom CSS with Fonts**

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

