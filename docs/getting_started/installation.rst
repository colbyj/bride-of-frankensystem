Install BOFS
============

The short version
-----------------

If you already know your way around Python:

1. **Install Python 3.9+.**
2. **Install the framework:** ``pip install bride-of-frankensystem``
3. **Test it:** run ``BOFS`` — you should see a help message.

That's the whole installation. The rest of this page walks through virtual-environment setup in detail. Once BOFS is installed, :doc:`initialize_project` covers creating and running your first project.

BOFS runs on Windows, Mac, and Linux.

Step 1: Install Python
----------------------

BOFS requires Python 3.9 or newer. Check what's already installed:

- **Windows**: Open Command Prompt (search "cmd") and run ``python --version``.
- **Mac/Linux**: Open Terminal and run ``python3 --version``.

If you see ``Python 3.9.x`` or higher, continue. Otherwise, download Python from https://python.org.

Step 2: Install BOFS
--------------------

Install BOFS into an isolated environment so its dependencies don't conflict with other Python projects on your machine. Pick whichever toolchain you're more comfortable with — both arrive at the same result.

.. note::
   If you only ever plan to work on a single BOFS project, you can skip the isolated environment and install BOFS into your system Python with ``pip install bride-of-frankensystem``. Working on multiple projects this way can cause dependency conflicts down the line.

.. tab-set::

   .. tab-item:: pip + venv

      The standard approach using Python's built-in tools.

      **2.1 Open your command line.**

      - **Windows**: Command Prompt or PowerShell
      - **Mac**: Terminal (via Spotlight)
      - **Linux**: your terminal application

      **2.2 Create the virtual environment.**

      .. code-block:: bash

         python -m venv bofs_venv

      This creates a ``bofs_venv`` folder containing its own copy of Python. Anything you install while the environment is active goes here instead of into your system Python, so different projects can use different package versions without conflicting.

      **2.3 Activate it.**

      - **Windows (Command Prompt)**: ``.\bofs_venv\Scripts\activate.bat``
      - **Windows (PowerShell)**: ``.\bofs_venv\Scripts\Activate.ps1``
      - **Mac/Linux**: ``source bofs_venv/bin/activate``

      Your prompt should now be prefixed with ``(bofs_venv)``. Subsequent ``python`` and ``pip`` commands will use the virtual environment. Activate it again each time you open a new terminal.

      **2.4 Install BOFS.**

      .. code-block:: bash

         pip install bride-of-frankensystem

      ``pip`` is Python's package installer. This downloads BOFS and its dependencies from the Python Package Index. It may take a minute or two.

      **2.5 Test the installation.** Run ``BOFS``. You should see a help message listing the available commands.

   .. tab-item:: uv

      `uv <https://docs.astral.sh/uv/>`_ is a Python package manager from Astral. Its ``uv tool`` command installs Python applications into isolated environments and adds them to your PATH, so you don't need to activate anything before running BOFS.

      **2.1 Install uv.** Follow the `uv installation instructions <https://docs.astral.sh/uv/getting-started/installation/>`_ for your operating system.

      **2.2 Install BOFS as a tool.**

      .. code-block:: bash

         uv tool install bride-of-frankensystem

      This creates a dedicated environment for BOFS behind the scenes and makes the ``BOFS`` command available globally. Open a new terminal afterwards so the updated PATH takes effect.

      **2.3 Test the installation.** Run ``BOFS``. You should see a help message listing the available commands.

Next step
---------

Continue to :doc:`initialize_project` to create your first project with ``BOFS init``.

Troubleshooting
---------------

- **"python not found"** — Make sure Python is installed and added to your system PATH.
- **"pip not found"** — On Windows, allow the installer to add Python to your PATH. On Linux, ``pip`` may be a separate package.
- **"BOFS not found"** — If you used pip + venv, make sure the virtual environment is activated. As a fallback, ``python -m BOFS run config.toml`` is equivalent to ``BOFS run config.toml``.
- **"Permission denied"** — Try your command line as administrator (Windows) or with ``sudo`` (Mac/Linux).
