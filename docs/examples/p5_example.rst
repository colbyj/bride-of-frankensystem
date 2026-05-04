P5 Example
==========

The ``p5_example`` project is a small BOFS study built around a custom JavaScript task written in `p5.js <https://p5js.org/>`_. Participants click on a canvas as fast as they can; their score is posted back to a BOFS-managed custom table when the task ends, and BOFS then advances them to the next page in the study.

The example is the canonical demonstration of three integration points that go beyond what the :doc:`minimal example </getting_started/quickstart_existing>` covers:

* A :doc:`simple page </getting_started/simple_custom_pages>` (``templates/simple/my_task.html``) that hosts the task's HTML and JavaScript without requiring any Python.
* A **custom database table** (``my_task``) defined by a JSON schema, so the task's data lives in its own table alongside BOFS's built-in ones.
* The built-in ``/table/<name>`` and ``/redirect_next_page`` routes, which let JavaScript push data into the database and advance the page flow without any extra Python.

Source: ``p5_example/`` in the `BOFS examples repository <https://github.com/colbyj/bride-of-frankensystem-examples/tree/master/p5_example>`_.

Running It
----------

From inside ``p5_example/`` after :doc:`installing BOFS </getting_started/installation>`:

.. code-block:: bash

    BOFS run p5_example.toml -d

The project listens on port 5002 by default; open http://localhost:5002 to step through the four pages — consent, instructions, the click task, and the end page with a completion code. The admin panel is at http://localhost:5002/admin (password ``example``).

What the Project Looks Like
---------------------------

.. image:: p5_example/page0.png
  :alt: Consent page.

.. image:: p5_example/page1.png
  :alt: Instructions page.

.. image:: p5_example/page2.png
  :alt: Task page — clickable canvas with a running score.

.. image:: p5_example/page3.png
  :alt: End page with the completion code.

Building It Yourself
--------------------

For a step-by-step walkthrough of how the project is wired together — directory layout, the JS task, the table schema, the configuration file — see :doc:`/getting_started/tutorial_js_task`.
