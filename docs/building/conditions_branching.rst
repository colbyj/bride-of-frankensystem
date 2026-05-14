Conditions and Branching
========================

Most experiments need at least some branching: A/B comparisons assign each participant to one of several conditions; pre-screening studies skip irrelevant follow-up questions; longitudinal studies carry condition assignments across sessions. BOFS handles all three with three primitives — ``CONDITIONS``, ``conditional_routing``, and ``show_if``.

Defining conditions
-------------------

Set ``CONDITIONS`` in ``config.toml`` to enable condition assignment:

.. code-block:: toml

   CONDITIONS = [
       {label="Control",       enabled=true},
       {label="High Reward",   enabled=true},
       {label="Low Reward",    enabled=true}
   ]

A few rules to keep in mind:

- **Participants are assigned to whichever enabled condition has the fewest participants** at the moment of assignment. This produces approximately balanced groups even with rolling recruitment.
- **Condition numbers start at 1**, in the order they appear in the list. ``Control`` is condition ``1``, ``High Reward`` is ``2``, ``Low Reward`` is ``3``.
- **Participants who haven't been assigned yet have condition ``0``.** This includes participants in projects with no ``CONDITIONS`` block at all.
- **Abandoned participants aren't counted when balancing.** "Abandoned" means inactive longer than ``ABANDONED_MINUTES`` (default 5 minutes). To include them, set ``COUNTS_INCLUDE_ABANDONED = true``.
- **Setting** ``enabled = false`` **removes a condition from rotation** without renumbering. Useful when one cell hits its target N before the others. You can also temporarily disable or enable conditions from the admin panel's progress page.

Where condition assignment happens
----------------------------------

Five routes can trigger condition assignment:

- ``consent`` and ``create_participant`` — assign on first arrival.
- ``consent_nc`` and ``create_participant_nc`` — do **not** assign (the ``_nc`` suffix means "no condition").
- ``assign_condition`` — a standalone PAGE_LIST entry. Triggers assignment if the participant doesn't already have a condition. Use this when consent was collected via one of the ``_nc`` variants and you want to assign later in the flow.

Once a participant has a condition, it doesn't change. The same participant returning to the project always sees the same branch.

Carrying conditions across sessions
-----------------------------------

For longitudinal studies, the second-session participant needs the same condition they were assigned on day 0. Two configuration settings handle this:

- ``CONDITIONS_FROM_DB = true`` looks up the returning participant by their external ID and reuses their prior condition. The lookup runs against the project's own participant database, so it works without exporting any data.
- ``CONDITIONS_FROM_CSV = "path/to/file.csv"`` pre-assigns conditions from a CSV file keyed by external ID. The file is two columns (external ID, condition number) and is read at startup.

The full longitudinal pattern, including how the participant arrives back at the second session, is covered in :doc:`longitudinal`.

Conditional routing
-------------------

The ``conditional_routing`` block in ``PAGE_LIST`` shows different page sequences to different conditions. Each branch has a ``condition`` number (and/or a ``show_if`` predicate) plus a nested ``page_list``:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",      path="consent"},
       {name="Demographics", path="questionnaire/demographics"},

       {conditional_routing=[
           {condition=1, page_list=[
               {name="Control Instructions",     path="instructions/control"},
               {name="Control Task",             path="custom/task_control"}
           ]},
           {condition=2, page_list=[
               {name="High Reward Instructions", path="instructions/high_reward"},
               {name="High Reward Task",         path="custom/task_high_reward"}
           ]},
           {condition=3, page_list=[
               {name="Low Reward Instructions",  path="instructions/low_reward"},
               {name="Low Reward Task",          path="custom/task_low_reward"}
           ]}
       ]},

       {name="Post-Task", path="questionnaire/post_task"},
       {name="End",       path="end"}
   ]

Each participant follows exactly one branch. The branches can have different lengths and different page types, but they should converge back to a shared post-task and end page (otherwise different conditions complete at different points).

A ``conditional_routing`` branch can also key off prior questionnaire answers using ``show_if`` instead of (or in addition to) ``condition``:

.. code-block:: text

   {conditional_routing=[
       {show_if="demographics.age < 18", page_list=[
           {name="Minor track", path="custom/task_minor"}
       ]},
       {show_if="demographics.age >= 18", page_list=[
           {name="Adult track", path="custom/task_adult"}
       ]}
   ]}

Both fields are optional. A branch matches when its ``condition`` matches (when set) and its ``show_if`` is true (when set); the first matching branch wins.

Page-level ``show_if``
----------------------

Any single PAGE_LIST entry — outside or inside a ``conditional_routing`` block — can carry a ``show_if`` predicate. When the predicate is false against the participant's stored answers, that page is skipped:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent",        path="consent"},
       {name="Demographics",   path="questionnaire/demographics"},
       {name="Parent contact", path="questionnaire/parent_contact", show_if="demographics.age < 18"},
       {name="End",            path="end"}
   ]

The expression has access to all of the participant's stored questionnaire fields, condition number, and custom-table export aggregates. The full syntax — operators, functions, qualified references for tagged questionnaires (``mood.pre.score``), table references (``tables.scores.high_score``) — is in :doc:`/reference/expressions`.

Accessing the condition in templates and routes
------------------------------------------------

Inside a Jinja template:

.. code-block:: html

   {% if session.condition == 1 %}
     <p>Control instructions go here.</p>
   {% elif session.condition == 2 %}
     <p>High-reward instructions go here.</p>
   {% endif %}

Inside a Python blueprint route, the condition is on the participant object passed to your view:

.. code-block:: python

   from flask import session
   condition = session['condition']  # int starting at 1, or 0 if unassigned

For more on the participant object and template variables, see :doc:`/framework/participant_data`.

A note on breadcrumbs
---------------------

If ``USE_BREADCRUMBS`` is enabled (the default) and the project uses ``conditional_routing`` or page-level ``show_if``, BOFS prints a startup warning. Breadcrumbs show every page in ``PAGE_LIST`` to every participant, which can leak the structure of conditions or hidden follow-up pages. Either disable breadcrumbs (``USE_BREADCRUMBS = false``) or accept that participants will see entries for pages they won't actually visit.

See also
--------

- The `A/B experiment example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/ab_experiment>`_ — two conditions with conditional routing in a complete project.
- The `branching example <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/branching_example>`_ — question-level and page-level ``show_if`` in one project.
- :doc:`longitudinal` for ``CONDITIONS_FROM_DB`` and ``CONDITIONS_FROM_CSV`` walkthroughs.
- :doc:`/reference/expressions` for full expression syntax.
