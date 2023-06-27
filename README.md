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
BOF requires Python 3.7+, along with the following Python packages.

* `flask` - The web framework that BOF is based off of.
* `sqlalchemy` - An object-relational manager that is used for database table definitions and query access.
* `flask-sqlalchemy` - A bridge between Flask and SQLAlchemy/
* `eventlet` - This is used as the production (live) web server, as an alternative to Flask's built in web server or the Apache web server.
* `toml` - The configuration files use the toml format.


Installation
============
It is highly recommended that you install BOFS in a virtual environment ([venv](https://docs.python.org/3/library/venv.html)). What 
this does is ensure that your project always has access to the version of BOF that it was developed with. 

The steps for doing this are:
1. Create the venv with: `python -m venv bofs_venv`
2. Activate the venv.
   * In Windows this is done via `.\bofs_venv\Scripts\activate.bat` if using `cmd` or `.\bofs_venv\Scripts\Activate.ps1` if using Powershell (the default command line in Windows 11).
   * In MacOS or Linux this is done via `source bofs_venv/bin/activate`
3. Download the project source code as a zip and install it via pip: `pip install bride-of-frankensystem-master.zip`
   * Or, you can download via pypi: `pip install -i https://test.pypi.org/simple/ bride-of-frankensystem`


Running BOFS
============
Once installed via `pip`, you can run your project by executing the `BOFS <your_config_file>` command in your project directory.
You can use the `-d` flag to enable debugging mode. If you are using PyCharm, then you can run it by adding a custom run
configuration with `BOFS` as the module name and your config file as the parameter.

If you installed BOFS via venv as suggested, then you will need to activate the virtual environment via step 2 of the installation instructions.


Further Help
============

* [Example Projects](https://github.com/colbyj/bride-of-frankensystem-examples)
* [Wiki](https://github.com/colbyj/bride-of-frankensystem/wiki)
* [Migrating to BOF 2.0](https://github.com/colbyj/bride-of-frankensystem/wiki/Migrating-to-BOFS-2.0)
