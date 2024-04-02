Instruction Pages
=================

It is possible to include static HTML pages that can be shown to your participants as part of the study. The intention
is the easy inclusion of instruction pages, but the pages can really be any static content that you like. The pages
make use of the theme utilized by the rest of your study and always show a "continue" button.

To make use of this, place a ``.html`` within your project into the ``/templates/instructions`` directory (of your project or
of your blueprint). For example: ``/templates/instructions/my_page.html``.

This page can then be added to your project's ``PAGE_LIST``, for example:

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='My Instructions', path='instructions/example_instructions'},
        {name='End', path='end'}
    ]

These html files are also Jinja2 templates, and therefore have access to the same variables.

See also :doc:`blueprints` (Templates (HTML) and Static Files) and :doc:`simple_pages`.