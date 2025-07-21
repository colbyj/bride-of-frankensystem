Overview
========

What is BOFS?
-------------
Bride of Frankensystem (BOFS) is **an open-source framework that bridges the gap between simple survey tools and complex custom experiments, designed by researchers for researchers.**

BOFS gives you complete control over your experiment flow and data collection. BOFS includes backend infrastructure, data management, and admin tools out of the box.

How BOFS Development Works
--------------------------

BOFS follows a simple workflow that lets you create experiments safely before sharing them with participants:

1. **Develop Locally**: You create and test your experiment on your own computer (called "local development"). Only you can see it while you're building it.

2. **Test and Debug**: You can preview exactly what participants will see, fix any issues, and make sure everything works perfectly.

3. **Deploy to Server**: When ready, you copy your experiment to a web server so participants anywhere can access it via a web link.


**Do I Need Programming Experience?**

For basic experiments (surveys, simple tasks, A/B testing), *minimal programming is required*. You'll work with configuration files and templates that use simple, readable formats. You can create simple custom pages by using HTML.

For advanced features (custom interactive tasks, complex data processing), *programming is helpful*. BOFS uses Python and web technologies, but provides a solid foundation to build on.

BOFS is perfect for behavioral researchers who need:

* **Custom experiment logic** that goes beyond simple questionnaires
* **Integration with external tasks** (JavaScript tasks, Unity WebGL games, etc.)
* **Complete data ownership** with no licensing fees or vendor lock-in
* **Production-ready features** like participant tracking, progress monitoring, and data export

Why Choose BOFS?
----------------

**vs. Survey Platforms (Qualtrics, Survey Monkey)**
  * More flexible for custom experiments
  * Better integration with external tasks  
  * Open source with no licensing fees
  * Programmer-friendly extensibility

**vs. JavaScript Libraries for Online Experiments (jsPsych, lab.js)**
  * Backend included with data management
  * Admin interface to track participant progress
  * Production-ready features (sessions, exports)
  * Leverage technologies you already know to build experimental tasks (e.g., Unity)

**vs. Building from Scratch**
  * Domain-specific features for behavioral research
  * Participant tracking and condition assignment built-in
  * Proven architecture used by real research labs
  * Extensive documentation and examples

Getting Started Paths
---------------------

**New to BOFS?** Start with the :doc:`installation guide <installation>`, then follow the :doc:`minimal quickstart tutorial </examples/quickstart>` to see BOFS in action.

**Need Simple Surveys?** Learn about :doc:`basic questionnaires </getting_started/basic_questionnaires>` and :doc:`simple custom pages </getting_started/simple_custom_pages>`.

**Running A/B Tests?** Check out :doc:`conditional routing and A/B testing </getting_started/project_configuration>` and the :doc:`A/B experiment example </examples/ab_experiment>`.

**Integrating Custom Tasks?** See :doc:`integrating JavaScript tasks </examples/integrating_js_task>` and :doc:`advanced custom pages </advanced/advanced_custom_pages>`.

**Deploying to Production?** Read about :doc:`server configuration </deployment/server_config>` and :doc:`MTurk/Prolific integration </deployment/mturk_prolific>`.

Key Features
------------
BOFS includes everything you need for online behavioral experiments:

**Core Experiment Features**
  * Automatic participant routing and progress tracking
  * Random condition assignment with balanced allocation
  * Built-in consent forms and completion codes
  * Session management with participant recovery

**Flexible Content System**
  * JSON-defined questionnaires with many question types
  * Static HTML pages for instructions and materials
  * Custom Flask blueprints for complex interactive tasks
  * Unity WebGL integration for games and simulations

**Data Management**
  * Automatic response storage with timestamps
  * Custom database tables for experiment-specific data
  * Real-time admin panel for monitoring progress
  * CSV export with configurable data formats

**Production Ready**
  * Bot and crawler detection
  * Honeypot implementation for data quality
  * Abandoned participant recovery
  * Integration with MTurk and Prolific

Citation
--------
If you use BOFS for your research, please cite it:

.. code-block:: bibtex

    @software{bride-of-frankensystem,
      author       = {Colby Johanson},
      title        = {colbyj/bride-of-frankensystem},
      month        = may,
      year         = 2024,
      publisher    = {Zenodo},
      version      = {2.0},
      doi          = {10.5281/zenodo.11176739},
      url          = {https://doi.org/10.5281/zenodo.11176739}
    }


Dependencies
------------
BOFS requires Python 3.9+, along with the following Python packages.

* ``flask`` - The web framework that BOF is based off of.
* ``sqlalchemy`` - An object-relational manager that is used for database table definitions and query access.
* ``flask-sqlalchemy`` - A bridge between Flask and SQLAlchemy.
* ``eventlet`` - This is used as the production (live) web server, as an alternative to Flask's built in web server or the Apache web server.
* ``toml`` - The configuration files use the toml format.

