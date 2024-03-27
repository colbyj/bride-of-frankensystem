Overview
========

Intended Uses
-------------
Bride of Frankensystem (BOF or BOFS) is intended to be used by developers to deploy custom-developed experiments online.
It provides a variety of solutions to common problems associated with online experiments while being easily extended in
a way that minimizes code duplication and encourages code reuse. Its design focuses on flexibility rather than providing
concrete solutions to every scenario, and so is targeted primarily towards software developers while still being
accessible for non-developers for many simple use-cases.

BOF is built using `Flask <https://flask.palletsprojects.com/>`_ and is intended to be used as a Python library. Because
it is built with Flask, all Flask extensions and features are supported, and it is relatively straightforward to extend
the project with your own custom web pages and tasks.

If you use this for your research, please cite it!

    Colby Johanson. (2022). colbyj/bride-of-frankensystem: 1.2 (1.2). Zenodo. https://doi.org/10.5281/zenodo.7487295


Features
--------
BOF includes a number of features relating to deploying online experiments

* Automatic :doc:`routing <routing/main>` between pages in a pre-defined order.
    * Built-in consent page in which the text can be easily configured.
    * Automatic random assignment of participants to various conditions, so different participants can be shown different pages.
* Define :doc:`questionnaires <questionnaires/main>` using a custom JSON structure.
* Show your own :doc:`simple web pages <instruction_pages>` defined via HTML (e.g., for instructions).
* Show more complex :doc:`custom web pages <blueprints>` (using Python and Flask) to embed custom tasks.
* Create :doc:`database tables <tables>` to record information about what your participants are doing.
* An admin panel to track participants' progress and export data.


Dependencies
------------
BOF requires Python 3.9+, along with the following Python packages.

* ``flask`` - The web framework that BOF is based off of.
* ``sqlalchemy`` - An object-relational manager that is used for database table definitions and query access.
* ``flask-sqlalchemy`` - A bridge between Flask and SQLAlchemy/
* ``eventlet`` - This is used as the production (live) web server, as an alternative to Flask's built in web server or the Apache web server.
* ``toml`` - The configuration files use the toml format.

