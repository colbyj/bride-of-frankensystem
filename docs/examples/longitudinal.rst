Longitudinal Experiment Example
===============================

A longitudinal study runs the same participants through several sessions,
typically days or weeks apart. BOFS does not (yet) have a single-config
"multi-day study" primitive — each session is configured as its own BOFS
project, with its own ``.toml`` and its own database. Participants are linked
across days by an external ID (a Prolific ID, MTurk Worker ID, etc.) entered
on each day's ``/external_id`` page.

The piece that needs the most care in this setup is **condition assignment**:
once you randomize a participant on day 1, every subsequent day must use the
same condition. Two config keys handle this without any custom code.

A complete worked example — two ``.toml`` files, a custom interactive task,
per-trial logging, and per-condition recall pages — lives in
`longitudinal_example/ <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/longitudinal_example>`__
in the BOFS examples repository. The snippets below are drawn from it.

Pre-assigning conditions by external ID
---------------------------------------

You have two interchangeable options. Either reads conditions for known
participants and applies them in place of the balancer.

``CONDITIONS_FROM_CSV``
    Path to a two-column CSV (``id,condition``). Read once at startup and
    cached in memory. Use this when you have an explicit list of participants
    and the conditions you want them in — for example, exporting day-1
    assignments as a CSV between days.

    .. code-block:: toml

        CONDITIONS_FROM_CSV = 'conditions_by_external_id.csv'

    Sample file:

    .. code-block:: text

        id,condition
        63e40d7b1a88578e3c993478,1
        59757b95395bf80001bf9daa,2
        5f2e00fa9832d716737ae694,1

    Condition values are 1-based and must fall within the configured
    ``CONDITIONS`` range.

``CONDITIONS_FROM_DB``
    A SQLAlchemy URI pointing at a previous day's BOFS database. The
    framework opens it read-only at startup and queries the ``participant``
    table by ``mTurkID`` when an ID is presented. Prefers a finished attempt
    over an unfinished one and the most recent over older ones; rows with
    ``condition`` of 0 or NULL (consent-only abandons) are ignored.

    .. code-block:: toml

        CONDITIONS_FROM_DB = 'sqlite:///day1.db'

    For a longitudinal study where day 1 already exists, this is usually
    simpler than maintaining a CSV — day 2 just points back at day 1's DB.

If both keys are set, the CSV is consulted first and the DB is the fallback.

Behavior on miss
^^^^^^^^^^^^^^^^

When at least one source is configured, an external ID that is **not** found
in any source produces a hard error: the participant is shown an
"ID not recognized" page and cannot proceed. This is intentional — for a
longitudinal study, an unknown ID means the person did not complete the
prior day's session and should not be in this one. There is no fallback to
the balancer; if you genuinely want mixed pre-assigned-plus-randomized
behavior, write a custom blueprint that calls the lookup service directly
(see below).

Page list ordering
------------------

For pre-assignment to work, the participant must have entered their external
ID *before* condition assignment runs. The standard pattern uses
``consent_nc`` (which does not auto-assign), then ``external_id``, then an
explicit ``assign_condition`` step:

.. code-block:: toml

    PAGE_LIST = [
        {name='Start', path='consent_nc'},
        {name='External ID', path='external_id'},
        {name='', path='assign_condition'},   # looks up CSV/DB, errors on miss
        # ... rest of the day's flow ...
        {name='End', path='end'},
    ]

If you use the regular ``/consent`` route, condition assignment runs at
consent — *before* ``/external_id`` — and the lookup will be skipped
(an empty external ID always falls through to the balancer). For
longitudinal studies you almost always want ``consent_nc`` plus explicit
``assign_condition`` so the lookup actually fires.

A complete two-day example
--------------------------

The ``longitudinal_example/`` project pairs two ``.toml`` files: day 1
randomizes participants via the standard balancer and writes their
assignments into its own database; day 2 reads that database back to
re-place returning participants.

**Day 1** — uses the standard ``/consent`` route, which assigns a balanced
condition at submission time. The Participant ID captured on the next page
is stored on that same participant row, which is what day 2 looks up:

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = 'sqlite:///longitudinal_day1.db'
    TITLE = 'Menu Learning Study - Day 1'

    CONDITIONS = [
        {label='Linear Menu', enabled=true},
        {label='Marking Menu', enabled=true},
    ]

    EXTERNAL_ID_LABEL = "Participant ID"

    PAGE_LIST = [
        {name='Consent', path='consent'},
        {name='Participant ID', path='external_id'},
        {name='Background', path='questionnaire/demographics'},
        {conditional_routing=[
            {condition=1, page_list=[{name='Practice', path='learn_linear'}]},
            {condition=2, page_list=[{name='Practice', path='learn_marking'}]},
        ]},
        {name='End', path='end'},
    ]

**Day 2** — uses ``consent_nc`` plus an explicit ``assign_condition`` step,
and points ``CONDITIONS_FROM_DB`` at day 1's database. ``CONDITIONS`` must
list the same labels in the same order so the integers line up:

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = 'sqlite:///longitudinal_day2.db'
    TITLE = 'Menu Learning Study - Day 2'

    CONDITIONS_FROM_DB = 'sqlite:///longitudinal_day1.db'

    CONDITIONS = [
        {label='Linear Menu', enabled=true},
        {label='Marking Menu', enabled=true},
    ]

    EXTERNAL_ID_LABEL = "Participant ID"

    PAGE_LIST = [
        {name='Consent', path='consent_nc'},
        {name='Participant ID', path='external_id'},
        {name='', path='assign_condition'},
        {conditional_routing=[
            {condition=1, page_list=[{name='Recall Test', path='recall_linear'}]},
            {condition=2, page_list=[{name='Recall Test', path='recall_marking'}]},
        ]},
        {name='Self-Report', path='questionnaire/recall'},
        {name='End', path='end'},
    ]

The full project — including the custom ``menu_task/`` blueprint, per-trial
``JSONTable`` logging, per-condition instruction pages, and a sample
``conditions.csv`` for the ``CONDITIONS_FROM_CSV`` alternative — is in
`longitudinal_example/ <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/longitudinal_example>`__.

Reading prior-day data programmatically
---------------------------------------

The lookup service also exposes the prior-study database for cases where
you need more than the condition — for example, a stratified balancer that
balances on a prior-day questionnaire response. Use it from a custom
blueprint:

.. code-block:: python

    from BOFS.services.condition_lookup import ConditionLookupService

    row = ConditionLookupService.find_prior_participant(p.mTurkID)
    if row is not None:
        # row is a dict-like view of the prior participant's row.
        # For arbitrary queries, ConditionLookupService.open_prior_db()
        # returns the underlying SQLAlchemy Engine.
        ...


