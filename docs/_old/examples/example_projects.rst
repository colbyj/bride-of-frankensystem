Example Projects
================

The `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples>`_ contains several runnable BOFS projects that illustrate different feature combinations. Clone or download the repository and run any of them with ``BOFS run <project>.toml -d`` from inside the project directory.

Minimal Example
---------------

A small project that exercises only the questionnaire system: consent, an example questionnaire shown twice with different "tags", a questionnaire that performs calculations on its responses, and an end page with a completion code. It's the recommended starting point for understanding what a BOFS project looks like end-to-end.

The :doc:`/getting_started/quickstart_existing` walks through running the minimal example. `Source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/minimal_example>`__.

A/B Experiment Example
----------------------

A two-condition between-subjects study: participants are randomly assigned to one of two menu styles and only see the instructions and task for that condition. The smallest example that uses ``CONDITIONS`` and ``conditional_routing``, with a custom blueprint that registers one route per condition and per-trial logging via a JSONTable.

See :doc:`ab_experiment` for a description, or `view the source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/ab_experiment>`__.

Advanced Example
----------------

Demonstrates most of BOFS's capabilities in a single project — multiple conditions, conditional routing, custom blueprints, custom database tables, instruction pages, and more. The right project to look at when you've got a feel for the basics and want to see how the larger pieces fit together.

See :doc:`advanced_example` for a description of what the project covers, or `view the source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/advanced_example>`__.

P5 Example
----------

A BOFS project built around a custom JavaScript task written in `p5.js <https://p5js.org/>`_. Demonstrates how to add a blueprint with its own static files, define a custom database table, and post task data back to BOFS from JavaScript.

See :doc:`p5_example` for a description of the project, or :doc:`/getting_started/tutorial_js_task` for a step-by-step walkthrough of how it's built. `Source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/p5_example>`__.

Tables and Expressions Example
------------------------------

A three-round clicker that captures every individual click into one detail table (``clicks``: round, click index, time-since-round-start, x, y), bulk-POSTs each round's clicks in a single request, and writes a one-row summary per round to a separate table (``scores``: round, score). The end-of-task results page is a single questionnaire whose JSON uses ``{{ tables.scores.high_score }}``, ``{{ tables.scores.round_score[1] }}``, etc. — no custom blueprint is needed to render personalized feedback. The shortest path to seeing the inline-expression substitution and the ``group_by`` subscript syntax in action.

See :doc:`tables_and_expressions_example` for a description, or `view the source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/tables_and_expressions_example>`__.

Branching Example
-----------------

A short project showing the two ``show_if`` features together: questions on a single page that appear or disappear based on what the participant has answered, and a page-level branch that picks one of two follow-up questionnaires based on a screening answer. The smallest example that uses ``show_if`` at both the question and page level.

See :doc:`branching_example` for a description, or `view the source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/branching_example>`__.

Unity Example
-------------

Two parallel projects (Unity 2021.1 and Unity 2023.2) showing one approach to embedding a Unity WebGL build inside a BOFS study. Each contains a ready-to-run BOFS project plus the Unity source project that produced the build. The integration covers hosting the WebGL build in three layouts (BOFS chrome, fullscreen, fully custom), pushing the participant ID and condition into Unity, posting data back from Unity into a custom BOFS table, and advancing the BOFS page flow from inside the Unity build.

See :doc:`unity_example` for a description. Source on GitHub: `unity_example_2021.1 <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/unity_example_2021.1>`_ and `unity_example_2023.2 <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/unity_example_2023.2>`_.

Longitudinal Example
--------------------

A two-session study where participants come back the next day and need to land in the same condition they were assigned the first day. Demonstrates ``CONDITIONS_FROM_DB`` (and the ``CONDITIONS_FROM_CSV`` alternative), ``consent_nc`` plus an explicit ``assign_condition`` step, and the page-list ordering that makes the lookup actually fire.

See :doc:`longitudinal` for a walkthrough of the mechanics, or `view the source on GitHub <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/longitudinal_example>`__.
