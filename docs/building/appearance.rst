Customizing the Appearance
==========================

BOFS pages use a default stylesheet defined with CSS custom properties. Two levels of customization are available without touching templates: a single config setting for the header color, and a full stylesheet override for broader changes. Template-level customization is covered in :doc:`/framework/templates_jinja`.

Quick: header color from config
--------------------------------

Set ``HEADER_COLOR`` in your project's ``.toml`` file to change the title bar background without creating a custom stylesheet:

.. code-block:: toml

    HEADER_COLOR = "#003366"   # hex, named color, rgb(), rgba(), hsl(), or hsla()

When ``HEADER_COLOR`` is unset, the default green from ``style.css`` is used. The accent also trickles into the question and navigation card borders (``--bofs-card-border`` uses ``color-mix()`` to produce a subtle tint), so a single color setting keeps the page visually cohesive.

See :doc:`/reference/configuration` for the full setting description.

Override the stylesheet
-----------------------

Placing a ``style.css`` in your project's ``static/`` directory replaces the BOFS default entirely. BOFS detects this file at startup and serves it in place of its own.

Copy the default as a starting point so you keep everything that already works:

.. code-block:: bash

    cp /path/to/BOFS/static/style.css ./static/style.css

Then edit ``./static/style.css`` and restart BOFS (``BOFS run config.toml -d``).

.. note::

    The exact path to the BOFS ``static/`` directory depends on how you installed the package. In a virtual environment it is typically something like ``venv/lib/python3.x/site-packages/BOFS/static/style.css``. You can also find it by running ``python -c "import BOFS, os; print(os.path.join(os.path.dirname(BOFS.__file__), 'static', 'style.css'))"`` from the project directory.

.. warning::

    A copied stylesheet will not receive updates automatically when BOFS is upgraded. Note the changes you make so you can reapply them to a fresh copy after an upgrade.

CSS custom properties
---------------------

The BOFS stylesheet uses CSS custom properties (variables) declared on ``:root``. Overriding a subset of them in your ``style.css`` is the most targeted way to restyle colors, fonts, and layout.

The full set of variables from the default stylesheet:

.. code-block:: css

    :root {
        /* Layout */
        --contents-width: 967px;

        /* Colors */
        --top-bar-color: #8CB737;
        --bs-border-color: black;

        /* Card surfaces */
        --bofs-card-bg: #ffffff;
        --bofs-card-border: color-mix(in srgb, var(--bofs-accent) 20%, #e2e5e7);

        /* Typography (rem values at 16px base) */
        --font-size-main: 1rem;            /* 16px */
        --font-size-h1: 1.5rem;            /* 24px */
        --font-size-h2: 1.3125rem;         /* 21px */
        --font-size-h3: 1.0625rem;         /* 17px */
        --font-size-h4: 0.9375rem;         /* 15px */
        --question-title-font-size: 1.0625rem;
        --question-instructions-font-size: 0.9375rem;
    }

To change only a few values, import the default and redeclare the variables you want to change:

.. code-block:: css

    @import url('/BOFS_static/style.css');

    :root {
        --top-bar-color: #003366;
        --font-size-main: 1.125rem;
        --contents-width: 800px;
    }

This keeps everything else — borders, question layout, mobile breakpoints — from the default.

.. note::

    The ``@import`` approach works when your ``static/style.css`` is meant to layer on top of the default rather than replace it. If you are making extensive changes, copying the full default and editing it directly may be easier to maintain.

Further customization
---------------------

For changes that require modifying HTML structure — overriding the base template, changing how question types render, or adding custom fonts and images — see :doc:`/framework/templates_jinja`. That page covers:

- Template lookup order (project ``templates/`` vs. BOFS defaults)
- Overriding ``template.html`` to change the page layout
- Custom question type templates
- Serving custom assets (fonts, images, JavaScript)
