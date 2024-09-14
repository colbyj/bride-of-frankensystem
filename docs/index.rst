.. Bride of Frankensystem documentation master file, created by
   sphinx-quickstart on Mon Mar 25 13:54:17 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Bride of Frankensystem's documentation!
==================================================

Welcome to Bride of Frankensystem's documentation! If you're just getting started, then start with the :doc:`overview`.

`Bride of Frankensystem <https://frankensystem.net>`_ (BOF or BOFS) is intended to be used by developers to deploy custom-developed experiments online. It provides a variety of solutions to common problems associated with online experiments while being easily extended in a way that minimizes code duplication and encourages code reuse. Its design focuses on flexibility rather than providing concrete solutions to every scenario, and so is targeted primarily towards software developers while still being accessible for non-developers for many simple use-cases.

BOF is built using Flask and is intended to be used as a Python library. Because it is built with Flask, all Flask extensions and features are supported, and it is relatively straightforward to extend the project with your own custom web pages and tasks.

.. toctree::
   :maxdepth: 2
   :caption: Introduction:

   overview
   installation
   quickstart
   integrating_js_task

.. toctree::
   :maxdepth: 2
   :caption: References:

   configuration
   routing/main
   routing/default_routes
   conditions
   questionnaires/main
   questionnaires/question_types
   questionnaires/custom_questions
   instruction_pages
   simple_pages
   blueprints
   tables
   util
