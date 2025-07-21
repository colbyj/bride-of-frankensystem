CLI Reference
=============

This page provides comprehensive documentation for the Bride of Frankensystem (BOFS) command-line interface.

Basic Usage
-----------

The basic syntax for running a BOFS project is:

.. code-block:: bash

    BOFS config_file.toml [OPTIONS]

Where ``config_file.toml`` is the path to your TOML configuration file that defines your experiment setup.

Command Line Options
--------------------

config (Required)
~~~~~~~~~~~~~~~~~

**Positional argument**

The name or path of the configuration file to load. This should be a TOML file containing your experiment configuration.

.. code-block:: bash

    BOFS minimal.toml
    BOFS /path/to/my/experiment.toml

--debug, -d
~~~~~~~~~~~

**Optional flag**

Toggles debug mode, which provides enhanced development features:

- Enables a debugging toolbar in the web interface
- Provides detailed error messages and stack traces
- Enables Flask's built-in debugger
- Shows more verbose logging output

.. code-block:: bash

    BOFS config.toml --debug
    BOFS config.toml -d

.. warning::
    Debug mode should **never** be used in production environments as it can expose sensitive information and security vulnerabilities.

--path, -p
~~~~~~~~~~~

**Optional parameter**

Specifies the working directory for your BOFS project. This is useful when your configuration file is in a different directory than your project files, or when you want to run BOFS from a different location.

.. code-block:: bash

    BOFS config.toml --path /path/to/project
    BOFS config.toml -p ./my_experiment

If not specified, BOFS will use the directory containing the configuration file as the working directory.

--reloader-off, -r
~~~~~~~~~~~~~~~~~~~

**Optional flag**

When running in debug mode, disables the automatic reloader feature. The reloader normally restarts the server automatically when code changes are detected.

.. code-block:: bash

    BOFS config.toml --debug --reloader-off
    BOFS config.toml -d -r

This option is only meaningful when used in combination with ``--debug`` mode.

Common Usage Patterns
----------------------

Basic Development
~~~~~~~~~~~~~~~~~

For standard development work:

.. code-block:: bash

    BOFS experiment.toml -d

This enables debug mode with auto-reloading for rapid development.

Production Testing
~~~~~~~~~~~~~~~~~~

For testing in a production-like environment:

.. code-block:: bash

    BOFS experiment.toml

This runs without debug mode, similar to how it would run in production.

Custom Project Directory
~~~~~~~~~~~~~~~~~~~~~~~~~

When your project files are in a specific directory:

.. code-block:: bash

    BOFS config.toml -p /home/researcher/experiments/study1

Debug Without Auto-reload
~~~~~~~~~~~~~~~~~~~~~~~~~~

For debugging without automatic restarts (useful when testing session persistence):

.. code-block:: bash

    BOFS experiment.toml -d -r

Running as Python Module
~~~~~~~~~~~~~~~~~~~~~~~~~

You can also run BOFS as a Python module:

.. code-block:: bash

    python -m BOFS config.toml
    python -m BOFS config.toml -d

This is particularly useful in environments where the ``BOFS`` command is not in your PATH.

Integration with Development Workflow
--------------------------------------

Virtual Environments
~~~~~~~~~~~~~~~~~~~~~

When using virtual environments, activate your environment first:

.. code-block:: bash

    # Linux/Mac
    source bofs_venv/bin/activate
    BOFS experiment.toml -d

    # Windows (Command Prompt)
    .\bofs_venv\Scripts\activate.bat
    BOFS experiment.toml -d

    # Windows (PowerShell)
    .\bofs_venv\Scripts\Activate.ps1
    BOFS experiment.toml -d

IDE Integration
~~~~~~~~~~~~~~~

**PyCharm Configuration:**

1. Go to Run → Edit Configurations
2. Add a new Python configuration
3. Set Module name to: ``BOFS``
4. Set Parameters to: ``your_config.toml -d``
5. Set Working directory to your project path

**VS Code Configuration:**

Add to your ``.vscode/launch.json``:

.. code-block:: json

    {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "BOFS Debug",
                "type": "python",
                "request": "launch",
                "module": "BOFS",
                "args": ["config.toml", "-d"],
                "cwd": "${workspaceFolder}",
                "console": "integratedTerminal"
            }
        ]
    }

Port Configuration
------------------

By default, BOFS runs on port 5000. You can specify a different port in your configuration file:

.. code-block:: toml

    PORT = 8080

The server will now be accessible at ``http://localhost:8080`` (or your specified port).

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

**Command not found:**

If you get a "command not found" error, ensure BOFS is properly installed:

.. code-block:: bash

    pip install bride-of-frankensystem

**Permission denied:**

On some systems, you may need to use ``python -m BOFS`` instead of the ``BOFS`` command directly.

**Config file not found:**

Ensure your configuration file path is correct and the file exists:

.. code-block:: bash

    ls -la config.toml  # Check if file exists
    BOFS ./config.toml  # Use relative path

**Port already in use:**

If port 5000 is already in use, either:

- Stop the other service using port 5000
- Change the ``PORT`` setting in your configuration file
- Kill any existing BOFS processes: ``pkill -f BOFS``

Debugging Tips
~~~~~~~~~~~~~~

**Enable verbose output:**

Use debug mode to see detailed error messages:

.. code-block:: bash

    BOFS config.toml -d

**Check configuration:**

Verify your TOML file is valid and contains required settings. Common required settings include:

- ``SQLALCHEMY_DATABASE_URI``
- ``SECRET_KEY``
- ``PAGE_LIST``

**Database issues:**

If you encounter database errors, check:

- Database file permissions (for SQLite)
- Database connection settings
- Whether the database file exists and is writable

Exit Codes
----------

BOFS uses standard exit codes:

- ``0``: Successful execution
- ``1``: General error (configuration issues, startup failures)
- ``2``: Command line argument errors

Environment Variables
---------------------

BOFS respects standard Flask environment variables:

- ``FLASK_ENV``: Set to ``development`` for enhanced debugging
- ``FLASK_DEBUG``: Set to ``1`` to enable debug mode (alternative to ``-d`` flag)

Note that command-line flags take precedence over environment variables.

See Also
--------

- :doc:`/getting_started/installation` - Installation instructions
- :doc:`/examples/quickstart` - Getting started guide
- :doc:`/reference/config_options` - Configuration reference
- :doc:`/getting_started/admin` - Admin panel documentation