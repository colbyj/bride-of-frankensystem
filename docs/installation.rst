Installation Instructions
=========================

These instructions cover two different ways in which you can install BOFS.

Installing Within a Virtual Environment
---------------------------------------

It is highly recommended that you install BOFS in a virtual environment (`venv <https://docs.python.org/3/library/venv.html>`_). What
this does is ensure that your project always has access to the version of BOF that it was developed with.

The steps for doing this type of install are:

1. Ensure that Python 3.9 (or newer) is installed on your machine and that ``pip`` is accessible via the command line.
2. Using the command line, create the venv with: ``python -m venv bofs_venv``
3. Activate the venv.

   * In Windows this is done via ``.\bofs_venv\Scripts\activate.bat`` if using ``cmd`` or ``.\bofs_venv\Scripts\Activate.ps1`` if using Powershell (the default command line in Windows 11).
   * In MacOS or Linux this is done via ``source bofs_venv/bin/activate``

4. Install BOFS via pip:

   * ``pip install bride-of-frankensystem`` for the latest release (recommended).
   * Or, for the latest development version, download the project source code as a zip and install it via pip: ``pip install bride-of-frankensystem-master.zip``

5. Ensure that you can execute the ``BOFS`` command. Try it without any arguments and you should see a help message.


System-Wide Installation
------------------------

An alternative approach to installing BOFS is to install it onto your system directly, so that you do not need a Python
venv for your project. This is more convenient, but it could cause trouble in the future for projects that depend on the
specific release of BOFS that existed at the time when the project was created (in the case of updates to BOFS).

The steps for doing this type of install are:

1. Ensure that Python 3.9 (or newer) is installed on your machine and that ``pip`` is accessible via the command line.
2. Using the command line, install BOFS: ``pip install bride-of-frankensystem``
3. Ensure that you can execute the ``BOFS`` command. Try it without any arguments and you should see a help message.

That's it!


Running BOFS
------------
Once installed via ``pip``, you can run your project by executing the ``BOFS <your_config_file>`` command in your project directory.
You can use the ``-d`` flag to enable debugging mode. If you installed BOFS via venv as suggested, then you will need to activate the virtual environment via step 2 of the installation instructions.

.. NOTE::
    If you are using PyCharm, then you can run it by adding a custom run configuration with `BOFS` as the module name and your config file as the parameter.
