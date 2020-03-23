Intended Uses
=============
Bride of Frankensystem (BOF or BOFS) is intended to be used by developers to deploy custom-developed experiments online. 
It provides a variety of solutions to common problems associated with online experiments while being easily extended in 
a way that minimizes code duplication and encourages code reuse. Its design focuses on flexibility rather than providing 
concrete solutions to every scenario, and so is targeted primarily towards software developers while still being 
accessible for non-developers for many simple use-cases.

BOF is built using [Flask](https://flask.palletsprojects.com/) and is intended to be used as a Python library. Because 
it is built with Flask, all Flask extensions and features are supported, and it is relatively straightforward to extend 
the project with your own custom web pages and tasks.

If you use this for your research, please cite it!
[![DOI](https://zenodo.org/badge/220541237.svg)](https://zenodo.org/badge/latestdoi/220541237)


Features
========
BOF includes a number of features relating to deploying online experiments
* Built-in consent page in which the text can be easily configured.
* Automatic random assignment of participants to various conditions.
* Define the experiment's flow in terms of URLs.
* Define questionnaires using a custom JSON structure.
* Create your own custom web pages (using Python and Flask) to embed custom tasks.
* Easily embed your own custom instructional pages without writing Python code.
* Admin panel to track participants' progress and export data.


Dependencies
============
BOF requires either Python 2.7.x or Python 3.x, along with the following Python packages.

* `future` - Used for Python 2 and 3 compatibility.
* `flask` - The web framework that BOF is based off of.
* `sqlalchemy` - An object-relational manager that is used for database table definitions and query access.
* `flask-sqlalchemy` - A bridge between Flask and SQLAlchemy
* `eventlet` - This is used as the production (live) web server, as an alternative to Flask's built in web server or the Apache web server.

Installation
============
Requires Python 2.7.x or Python 3.x. 

The preferred method of installation is to download the zip file and run: 
`pip install bride-of-frankensystem-master.zip` 
from directory in which the file is located.
This should also install all required packages using `pip`. 

Further Help
============

* [Example Projects](https://github.com/colbyj/bride-of-frankensystem-examples)
* [Wiki](https://github.com/colbyj/bride-of-frankensystem/wiki)
