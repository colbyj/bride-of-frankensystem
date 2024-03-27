Instruction Pages
=================

It is possible to include static HTML pages that can be shown to your participants as part of the study. The intention
is the easy inclusion of instruction pages, but the pages can really be any static content that you like.

To make use of this, place a ``.html`` within your project into the ``/templates/instructions`` directory. For example,
``/templates/instructions/example_instructions.html``.

This page can then be added to your project's ``PAGE_LIST``, for example:

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='My Instructions', path='instructions/example_instructions'},
        {name='End', path='end'}
    ]

