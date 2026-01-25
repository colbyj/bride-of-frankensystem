Installation Instructions
=========================

This guide will help you install BOFS on your computer so you can create and test experiments locally before deploying them for participants.

**What You'll Need**
- A computer running Windows, Mac, or Linux
- About 15 minutes
- An internet connection for downloading software

**What We'll Install**
- **Python**: The programming language BOFS is built with
- **BOFS**: The framework itself
- **A text editor**: For editing configuration files (optional but recommended)

Step 1: Install Python
-----------------------

BOFS requires Python 3.9 or newer. Check if you already have Python:

**Windows**: Open Command Prompt (search "cmd") and type: ``python --version``

**Mac/Linux**: Open Terminal and type: ``python3 --version``

If you see something like "Python 3.9.x" or higher, you're good! If not, download Python from https://python.org.

Step 2: Install BOFS (Recommended Method)
------------------------------------------

We'll install BOFS in a "virtual environment" - think of this as a separate workspace that keeps BOFS organized and prevents conflicts with other software.

**2.1 Open Your Command Line**

- **Windows**: Search for "Command Prompt" or "PowerShell" and open it
- **Mac**: Search for "Terminal" in Spotlight
- **Linux**: Open your terminal application

**2.2 Create a Workspace for BOFS**

Type this command and press Enter:
``python -m venv bofs_venv``

This creates a folder called "bofs_venv" that will contain BOFS and its dependencies.

**2.3 Activate Your Workspace**

**Windows (Command Prompt)**: ``.\bofs_venv\Scripts\activate.bat``

**Windows (PowerShell)**: ``.\bofs_venv\Scripts\Activate.ps1``

**Mac/Linux**: ``source bofs_venv/bin/activate``

You should see "(bofs_venv)" appear at the beginning of your command line, indicating the workspace is active.

**2.4 Install BOFS**

Type this command: ``pip install bride-of-frankensystem``

This downloads and installs BOFS. It may take a few minutes.

**2.5 Test the Installation**

Type: ``BOFS``

You should see a help message listing BOFS commands. If you see this, congratulations - BOFS is installed!


Alternative: Simple Installation
----------------------------------

If you prefer a simpler approach (though less recommended for multiple projects):

1. Open your command line
2. Type: ``pip install bride-of-frankensystem``
3. Test by typing: ``BOFS``

This installs BOFS system-wide but may cause issues if you work on multiple BOFS projects over time.

Step 3: Get a Text Editor or IDE
--------------------------------

You'll need to edit text files (configuration files, HTML templates). While you can use basic text editors like Notepad, these editors make the process much easier:

- **Visual Studio Code** (free, excellent for beginners): https://code.visualstudio.com
- **Sublime Text**: https://www.sublimetext.com
- **Atom**: https://atom.io

These editors can be extended via plugins to better support Python code, but this isn't strictly necessary.

Alternatively, download a fully-featured IDE such as PyCharm, which is specifically designed to work with Python projects.

- **PyCharm**: https://www.jetbrains.com/pycharm/

Step 4: Try Your First Experiment
----------------------------------

1. **Download Example Projects**: Get the examples from `here <https://github.com/colbyj/bride-of-frankensystem-examples/archive/refs/heads/master.zip>`_ and unzip them.

2. **Navigate to the Example**: Open your command line and navigate to the minimal example folder.

3. **Activate BOFS** (if you used the virtual environment): Run the activation command from Step 2.3 above.

4. **Run the Example**: Type ``BOFS run minimal.toml -d``

5. **View Your Experiment**: Open a web browser and go to ``http://localhost:5000``

You should see a working experiment! Press Ctrl+C in the command line to stop it.

**What Just Happened?**

- BOFS read the ``minimal.toml`` configuration file
- It started a local web server on your computer
- You accessed your experiment through your web browser
- The ``-d`` flag enabled debug mode (helpful while developing)

Next Steps
----------

- Continue with the :doc:`/examples/quickstart` to understand how the example works
- Read about :doc:`/getting_started/project_configuration` to learn how to configure experiments
- When ready to deploy for participants, see :doc:`/deployment/server_config`

**Troubleshooting**

- **"python not found"**: Make sure Python is installed and added to your system PATH.
- **"pip not found"**: If on Windows, make sure you allowed the installer to allow Python to your PATH. If on Linux, you may need to install ``pip`` separately.
- **"BOFS not found"**: Make sure you activated your virtual environment (Step 2.3) and that BOFS was installed via ``pip``. You can also try ``python -m BOFS run config.toml``, which is equivalent.
- **"Permission denied"**: Try running your command line as administrator (Windows) or using ``sudo`` (Mac/Linux).
- **"Address Already in Use"**: Try configuring your project to work with a different port (by editing the ``.toml`` config file).

**Remember**: Each time you want to work with BOFS, you'll need to activate your virtual environment first (Step 2.3).
