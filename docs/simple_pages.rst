Simple HTML Pages
=================

You can show simple HTML pages as part of your study. These are similar to the instruction pages, but *no* "continue"
button is shown, so you have to implement your own redirection (for example, to ``/redirect_next_page``).

To make use of this, place a ``.html`` within your project into the ``/templates/simple`` directory (of your project or
of your blueprint). For example: ``/templates/simple/my_page.html``.

This page can then be added to your project's ``PAGE_LIST``, for example:

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='My Instructions', path='simple/my_page'},
        {name='End', path='end'}
    ]

These html files are also Jinja2 templates, and therefore have access to the same variables.

See also :doc:`blueprints` (Templates (HTML) and Static Files) and :doc:`instruction_pages`.

