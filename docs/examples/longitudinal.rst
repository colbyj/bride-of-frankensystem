Longitudinal Experiments
========================

A longitudinal study runs the same participants through several sessions,
typically days or weeks apart. BOFS does not (yet) have a single-config
"multi-day study" primitive — each session is configured as its own BOFS
project, with its own ``.toml`` and its own database. Participants are linked
across days by an external ID (a Prolific ID, MTurk Worker ID, etc.) entered
on each day's ``/external_id`` page.

The piece that needs the most care in this setup is **condition assignment**:
once you randomize a participant on day 0, every subsequent day must use the
same condition. Two config keys handle this without any custom code.

Pre-assigning conditions by external ID
---------------------------------------

You have two interchangeable options. Either reads conditions for known
participants and applies them in place of the balancer.

``CONDITIONS_FROM_CSV``
    Path to a two-column CSV (``id,condition``). Read once at startup and
    cached in memory. Use this when you have an explicit list of participants
    and the conditions you want them in — for example, exporting day-0
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

        CONDITIONS_FROM_DB = 'sqlite:///day0.db'

    For a longitudinal study where day 0 already exists, this is usually
    simpler than maintaining a CSV — day 1 just points back at day 0's DB.

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

A complete day-1 example
------------------------

.. code-block:: toml

    SQLALCHEMY_DATABASE_URI = 'sqlite:///stress_hexagon_day1.db'
    TITLE = 'Stress Hexagon — Day 1'
    ADMIN_PASSWORD = 'changeme'

    CONDITIONS = [{label='Stress'}, {label='No Stress'}]
    CONDITIONS_FROM_DB = 'sqlite:///stress_hexagon_day0.db'

    EXTERNAL_ID_LABEL = "Prolific ID"
    EXTERNAL_ID_PROMPT = "Please enter your Prolific ID now."

    PAGE_LIST = [
        {name='Start', path='consent_nc'},
        {name='External ID', path='external_id'},
        {name='', path='assign_condition'},
        {name='Questionnaire', path='sam/before'},
        {conditional_routing=[
            {condition=1, page_list=[{name='Task', path='pasat'}]},
            {condition=2, page_list=[{name='Task', path='sparkle'}]},
        ]},
        {name='Questionnaire', path='sam/after'},
        {name='End', path='end'},
    ]

Day 0 has its own ``.toml`` that *doesn't* set ``CONDITIONS_FROM_*`` — it
randomizes via the normal balancer and writes those assignments into
``stress_hexagon_day0.db``. Day 1 (above) reuses those assignments by
pointing back at that file.

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

Aspects not yet covered
-----------------------

The following aspects of longitudinal studies are not yet handled by BOFS
itself and remain on the researcher to coordinate externally:

- Sending day-N reminder emails or scheduling day-N invitations.
- Joining the per-day databases for analysis (typically done offline by
  ``mTurkID``).
- A single shared participant registry across days.

These are tracked for a future native multi-session feature.
