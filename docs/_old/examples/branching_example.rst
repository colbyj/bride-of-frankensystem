Branching Example
=================

A short demonstration of the two ``show_if`` features together: questions on a single page that appear or disappear based on what the participant has answered so far, and a page-level branch that picks one of two follow-up questionnaires based on a screening answer.

Source: ``branching_example/`` in the `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/branching_example>`_.

What It Demonstrates
--------------------

* **Question-level** ``show_if`` — the screening questionnaire shows different follow-up fields depending on whether the participant says they exercise regularly. The "please specify" field is gated on a *conditionally shown* dropdown's value, so it only appears when both the parent dropdown is visible and ``Other`` is selected.
* **Page-level** ``show_if`` — two follow-up questionnaires (``active_followup`` and ``inactive_followup``) appear in ``PAGE_LIST``, each with a predicate that picks one based on the screening answer. The other is removed from the participant's flow and skipped by next/back navigation.
* **Cross-questionnaire reference** in a page-level predicate — ``screening.exercises_regularly`` qualifies the field with the questionnaire it came from.

For the syntax itself, the full set of operators and functions, and the qualified reference forms for tagged questionnaires, see :doc:`/advanced/expressions`.

Running It
----------

From inside ``branching_example/`` after :doc:`installing BOFS </getting_started/installation>`:

.. code-block:: bash

    BOFS branching.toml -d

The project listens on port 5006 by default. Open http://localhost:5006 to step through the experiment, or http://localhost:5006/admin (password ``example``) to inspect participant progress and export data.
