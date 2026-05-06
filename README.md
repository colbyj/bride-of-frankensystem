Bride of Frankensystem
======================
Bride of Frankensystem (BOFS) is an open-source framework for building online behavioral experiments and surveys.
You describe your study in plain-text files: a TOML config for settings and page flow, JSON files for questionnaires, 
and HTML files for custom pages. BOFS handles participant routing, condition assignment, consent forms, data storage, 
and provides an admin panel for monitoring and export.

BOFS is built on [Flask](https://flask.palletsprojects.com/). When the patterns built into BOFS aren't enough, custom
Flask routes can be added to the same project.

If you use BOFS for your research, please cite it!
[![DOI](https://zenodo.org/badge/220541237.svg)](https://zenodo.org/badge/latestdoi/220541237)


Where BOFS fits
===============
If you've used other tools for online studies, here's where BOFS sits relative to them:

* Survey platforms like Qualtrics, SurveyMonkey, and Google Forms handle questionnaires through a point-and-click
  editor on hosted infrastructure. They can't embed a custom JavaScript task or open the data layer for custom logic.
* jsPsych and lab.js handle in-browser trial logic (precise timing, key capture, randomization), but don't host the
  surrounding study — consent, condition assignment, sessions, admin panel. A jsPsych or lab.js task can run inside a
  BOFS custom page.
* Building from scratch in Flask, Django, or Express works too, but every piece of the surrounding study is yours to
  write.

BOFS lands in the middle: the surrounding scaffolding is provided for you, and the boundary is open enough to drop in
JavaScript, custom HTML, or Python where you need it.


Documentation & Examples
========================
* [Documentation (HTML)](https://bride-of-frankensystem.readthedocs.io/en/latest/)
* [Documentation (PDF)](https://bride-of-frankensystem.readthedocs.io/_/downloads/en/latest/pdf/)
* [Example Projects](https://github.com/colbyj/bride-of-frankensystem-examples)
* [Migrating to BOF 2.0](https://github.com/colbyj/bride-of-frankensystem/wiki/Migrating-to-BOFS-2.0)


Features
========
* Built-in consent page. Edit the wording in an HTML file at the project root.
* Random assignment to conditions, with balancing as participants enroll.
* Experiment flow defined as a list of pages in your config file.
* Questionnaires defined in JSON: item-order shuffling, conditional questions and pages, and computed scores at
  submission time.
* Reuse earlier answers — for instance, embed a participant's prior rating into the wording of a later question.
* Repeated measurements, either within a session (pre/post) or across days and weeks via an external ID that resumes
  the participant's condition.
* Custom JSON-defined database tables for trial-by-trial events, task scores, mouse movement, or anything else your
  study generates. JavaScript POSTs to `/table/<name>`; rows show up in the admin panel.
* Static file serving for stimuli (images, audio, video), PDFs, and any JS libraries your custom pages need.
* MTurk and Prolific external-ID handling, with configurable completion-code redirects.
* Custom Python/Flask routes for embedded tasks or other server-side logic.
* Instruction and simple pages built from HTML alone, no Python required.
* Admin panel with live participant progress, per-condition descriptive statistics (N, mean, SD, median, box plots),
  and data export.


Dependencies
============
BOFS requires Python 3.9+, along with the following Python packages:

* `flask` - the web framework BOFS is built on.
* `flask-wtf` - form handling and CSRF.
* `flask-sqlalchemy` - bridge between Flask and SQLAlchemy.
* `sqlalchemy` - ORM used for database table definitions and queries.
* `flask-compress` - supports the compressed assets that Unity WebGL builds use.
* `waitress` - production WSGI server; an alternative to Flask's built-in server or Apache.
* `toml` - configuration files use the TOML format.
* `crawlerdetect` - filters out web crawlers so they aren't counted as participants.
* `pandas` - data export and the admin results preview.
* `questionary` - interactive prompts in the `BOFS init` wizard.
* `bleach` - HTML sanitization for user-supplied content.


Installing and Running BOFS
===========================
Refer to the [installation instructions](https://docs.frankensystem.net/en/latest/getting_started/installation.html) in
the documentation.

Once installed, run `BOFS init` to generate a new project.
