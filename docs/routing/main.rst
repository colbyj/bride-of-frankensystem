Routing Participants
====================

As explained within :doc:`../quickstart` and :doc:`../configuration`, the configuration file contains a ``PAGE_LIST`` variable
that is used to configure how participants are routed through the study. There is no limit on the number of pages you
can use in your experiment, but there are two pages you need to include in your project at a minimum.

The first page must be one of the following pages:

.. table:: Routes you can use for your first page
    :widths: 30,50

    =========================== =============
    Route                       Description
    =========================== =============
    ``/consent``                This shows a consent form. Upon submission, the participant entry is created in the database, they are assigned a condition, and the session variables are set.
    ``/consent_nc``             This is the same as ``/consent``, except that the participant is not assigned a condition (defaults to 0).
    ``/create_participant``     This creates the participant entry in the database, assigns a condition to the participant, and their session variables are set. Does not show a consent form and instead automatically redirects them to the next page.
    ``/create_participant_nc``  This is the same as ``/create_participant``, except that the participant is not assigned a condition (defaults to 0).
    =========================== =============

And the last page must be ``/end``. So the simplest study would just show the participant a consent page and then the
final page, which would show a message or a message and a completion code.

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='End', path='end'}
    ]

Further pages can be added to the ``PAGE_LIST`` as needed. For an overview of the available pages, see :doc:`default_routes`.

For example, we could add a questionnaire to the PAGE_LIST, so that the participant must complete a questionnaire before the study ends.

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='Questionnaire', path='questionnaire/example'},
        {name='End', path='end'}
    ]

You could also define your own pages (see :doc:`../blueprints`) and use these within ``PAGE_LIST``.

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='My Custom Page', path='my_page'},
        {name='End', path='end'}
    ]

Routing by Condition
--------------------
If using conditions (see :doc:`../configuration`), then one simple way of making use of these is within the ``PAGE_LIST``.
Here, you can define specific page sequences for users based on their assigned condition number. These are added in
place of a single page. For example:

.. code-block:: toml

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='Questionnaire', path='questionnaire/example'},
        {conditional_routing=[
            {condition=1, page_list=[
                {name='Task Instructions', path='instructions/1'}
            ]},
            {condition=2, page_list=[
                {name='Task Instructions', path='instructions/2'}
            ]}
        ]},
        {name='End', path='end'}
    ]
