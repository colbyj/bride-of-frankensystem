Installation Instructions
=========================

BOFS runs on Windows, Mac, and Linux. You'll install Python, then BOFS itself, then a text editor to work with configuration files.

Step 1: Install Python
-----------------------

BOFS requires Python 3.9 or newer. Check if you already have Python:

**Windows**: Open Command Prompt (search "cmd") and type: ``python --version``

**Mac/Linux**: Open Terminal and type: ``python3 --version``

If you see something like "Python 3.9.x" or higher, you're good! If not, download Python from https://python.org.

Step 2: Install BOFS
--------------------

Install BOFS into an isolated environment so its dependencies don't conflict with other Python projects on your machine. Pick whichever toolchain you're more comfortable with — both arrive at the same result.

.. note::
   If you only ever plan to work on a single BOFS project, you can skip the isolated environment entirely and install BOFS into your system Python with ``pip install bride-of-frankensystem``. Working on multiple projects this way can cause dependency conflicts down the line.

.. tabs::

   .. tab:: pip + venv

      The standard approach using Python's built-in tools.

      **2.1 Open Your Command Line**

      - **Windows**: Command Prompt or PowerShell
      - **Mac**: Terminal (via Spotlight)
      - **Linux**: your terminal application

      **2.2 Create the Virtual Environment**

      ``python -m venv bofs_venv``

      This creates a ``bofs_venv`` folder containing its own copy of Python. Anything you install while the environment is active goes here instead of into your system Python, so different projects can use different package versions without conflicting.

      **2.3 Activate It**

      **Windows (Command Prompt)**: ``.\bofs_venv\Scripts\activate.bat``

      **Windows (PowerShell)**: ``.\bofs_venv\Scripts\Activate.ps1``

      **Mac/Linux**: ``source bofs_venv/bin/activate``

      Your prompt should now be prefixed with ``(bofs_venv)``, which means subsequent ``python`` and ``pip`` commands will use the virtual environment. You'll need to activate the environment again each time you open a new terminal.

      **2.4 Install BOFS**

      ``pip install bride-of-frankensystem``

      ``pip`` is Python's package installer. This downloads BOFS and its dependencies from the Python Package Index and installs them into your virtual environment. It may take a minute or two.

      **2.5 Test the Installation**

      Run ``BOFS``. You should see a help message listing the available commands.

   .. tab:: uv

      `uv <https://docs.astral.sh/uv/>`_ is a faster, newer Python package manager from Astral. Its ``uv tool`` command installs Python applications into their own isolated environments and adds them to your PATH, so you don't need to activate anything before running BOFS.

      **2.1 Install uv**

      Follow the `uv installation instructions <https://docs.astral.sh/uv/getting-started/installation/>`_ for your operating system.

      **2.2 Install BOFS as a Tool**

      ``uv tool install bride-of-frankensystem``

      This creates a dedicated environment for BOFS behind the scenes and makes the ``BOFS`` command available globally. Open a new terminal afterwards so the updated PATH takes effect.

      **2.3 Test the Installation**

      Run ``BOFS``. You should see a help message listing the available commands.

Step 3: Get a Text Editor or IDE
--------------------------------

You'll be editing config files and HTML templates. Any text editor works; these have syntax highlighting and project navigation that make the job easier:

- **Visual Studio Code** (free): https://code.visualstudio.com
- **Sublime Text**: https://www.sublimetext.com
- **PyCharm** (full IDE, with Python tooling built in): https://www.jetbrains.com/pycharm/

Next Steps
----------

You're ready to build a BOFS project. There are two starting points:

* :doc:`quickstart_create` — generate a fresh project from scratch with the ``BOFS init`` wizard.
* :doc:`quickstart_existing` — download the examples repository and run the *minimal example* to see a working project end-to-end.

When you're ready to put your project in front of real participants, see :doc:`/deployment/server_config`.

Troubleshooting
---------------

- **"python not found"**: Make sure Python is installed and added to your system PATH.
- **"pip not found"**: On Windows, make sure you allowed the installer to add Python to your PATH. On Linux, you may need to install ``pip`` separately.
- **"BOFS not found"**: If you used pip + venv, make sure your virtual environment is activated. As a fallback, ``python -m BOFS run config.toml`` is equivalent to ``BOFS run config.toml``.
- **"Permission denied"**: Try running your command line as administrator (Windows) or using ``sudo`` (Mac/Linux).
- **"Address already in use"**: Another program is using the same port. Edit your project's ``.toml`` file to set a different ``PORT``.
