Adding Your Own Pages
=====================

BOFS supports three kinds of custom pages that don't require any Python:

- **Instruction pages** — static HTML with an automatic "Continue" button.
- **Simple pages** — HTML rendered inside the BOFS chrome (header, breadcrumbs, project styling), but no automatic Continue button.
- **Custom pages** — the template is the entire HTML document with no BOFS wrapping.

All three are HTML files placed in your project's ``templates/`` directory and referenced in ``PAGE_LIST`` by their path.

Instruction pages
-----------------

An instruction page displays static HTML content. BOFS wraps it in the project's standard layout and adds a "Continue" button at the bottom that advances to the next page in ``PAGE_LIST``.

Place the file in ``templates/instructions/`` and reference it in ``PAGE_LIST`` as ``instructions/<filename>`` (without the ``.html`` extension).

``templates/instructions/welcome.html``:

.. code-block:: html

   <h2>Welcome to Our Study</h2>

   <p>Thank you for participating. This experiment will take approximately 15 minutes.</p>

   <p>During this study, you will:</p>
   <ul>
       <li>Answer some demographic questions</li>
       <li>Complete a short task</li>
       <li>Provide feedback about your experience</li>
   </ul>

   <p><strong>Important:</strong> Please complete this study in one sitting.</p>

Then add the page to your configuration:

.. code-block:: toml

   PAGE_LIST = [
       {name="Consent", path="consent"},
       {name="Welcome", path="instructions/welcome"},
       {name="Demographics", path="questionnaire/demographics"},
       {name="End", path="end"}
   ]

Instruction pages are Jinja2 templates, so you can embed session variables and conditional logic. See :doc:`/framework/templates_jinja` for details.

Simple pages
------------

A simple page is rendered inside the BOFS chrome — the participant sees the same header and breadcrumbs as the rest of the experiment — but there is no automatic Continue button. Your HTML controls when and how the participant advances.

Place the file in ``templates/simple/`` and reference it in ``PAGE_LIST`` as ``simple/<filename>``.

To advance the participant, link or redirect to one of these routes:

- ``/redirect_next_page`` — go to the next page in ``PAGE_LIST``.
- ``/redirect_to_page/<path>`` — go to a specific page (e.g., ``/redirect_to_page/questionnaire/demographics``).

See :doc:`/reference/built_in_routes` for the full redirect route reference.

This example shows an instruction page where the Continue button only appears after a 10-second delay:

``templates/simple/timed_instructions.html``:

.. code-block:: html

   <h2>Task Instructions</h2>

   <p>Read these instructions carefully before proceeding.</p>

   <div id="continue-area" style="display: none;">
       <p>You may now continue.</p>
       <button onclick="location.href='/redirect_next_page'">I'm Ready to Begin</button>
   </div>

   <script>
   setTimeout(function () {
       document.getElementById('continue-area').style.display = 'block';
   }, 10000);
   </script>

``PAGE_LIST`` entry:

.. code-block:: toml

   PAGE_LIST = [
       {name="Instructions", path="simple/timed_instructions"},
       {name="Task", path="custom/my_task"},
       {name="End", path="end"}
   ]

Custom pages
------------

A custom page renders your template as the complete HTML document. BOFS adds no header, breadcrumbs, or stylesheet. Use this when the task needs full control over the page — for example, a jsPsych, lab.js, PsychoJS, p5.js, or Unity experiment that must occupy the entire viewport or supply its own ``<head>``.

Place the file in ``templates/custom/`` and reference it in ``PAGE_LIST`` as ``custom/<filename>``.

``templates/custom/my_task.html``:

.. code-block:: html

   <!DOCTYPE html>
   <html lang="en">
   <head>
       <meta charset="UTF-8">
       <title>My Task</title>
   </head>
   <body>
       <main></main>
       <script src="/static/my_task.js"></script>
   </body>
   </html>

Custom pages are still Jinja2 templates and have access to the same template variables (``session``, ``participant``, ``config``, ``debug``) as instruction and simple pages. The same redirect routes apply: ``/redirect_next_page``, ``/redirect_to_page/<path>``, or a POST to the page's own route.

See :doc:`/getting_started/quickstart_custom_task` for a worked example of a JavaScript task using a custom page.

Serving static files
--------------------

BOFS serves everything in your project's ``static/`` directory at the URL path ``/static/``. Reference files from any template using ``/static/<path>``.

Common uses: stimulus images, videos, audio files, downloadable PDFs, and JavaScript task bundles.

Example project layout:

.. code-block:: text

   your_project/
   ├── static/
   │   ├── images/
   │   │   └── stimulus.jpg
   │   └── audio/
   │       └── instructions.mp3
   └── templates/
       └── instructions/
           └── welcome.html

Displaying an image in an instruction page:

.. code-block:: html

   <h2>Study Materials</h2>

   <img src="/static/images/stimulus.jpg" alt="Stimulus image" width="400">

Choosing between the three page types
--------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Type
     - Use when
   * - Instruction
     - You want static informational content with the standard Continue button and project styling.
   * - Simple
     - You need project styling but want to control navigation yourself (e.g., a timer, a quiz gate, a custom form).
   * - Custom
     - The task needs the full HTML document — its own ``<head>``, full-viewport layout, or a JavaScript framework that conflicts with the BOFS chrome.

For pages that display dynamic content based on session data, questionnaire responses, or configuration variables, see :doc:`/framework/templates_jinja`.

For pages that need server-side logic (Python routes, form handling, database writes), see :doc:`/framework/blueprints_routes`.
