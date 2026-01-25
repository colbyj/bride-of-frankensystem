import os
import sys
import argparse
from .create_app import create_app


def run_server(args):
    """Run the BOFS server with the specified configuration."""
    if args.path:
        path = os.path.abspath(args.path)
        config_name = args.config
    else:
        # Set the path based on the path of the config file.
        abs_config = os.path.abspath(args.config)
        path = os.path.dirname(abs_config)
        config_name = os.path.basename(abs_config)

    # Default to current directory if path is empty (config file in current dir)
    if not path:
        path = os.getcwd()

    try:
        app = create_app(path, config_name, args.debug, args.reloader_off)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if app is None:
        sys.exit(1)

    port = 5000  # Default to port 5000 if it's not set.

    if "PORT" in app.config:
        port = app.config["PORT"]

    # Update sys.argv with resolved paths so the reloader works correctly.
    # When Flask's reloader restarts, it uses sys.argv, and after os.chdir()
    # in create_app, relative paths in the original argv may no longer be valid.
    if args.debug and not args.reloader_off:
        sys.argv = [sys.argv[0], 'run', '-d', '--path', path, config_name]

        # Ensure PYTHONPATH includes the BOFS package location so the reloader
        # subprocess can find it after os.chdir() changes the working directory.
        import BOFS
        bofs_parent_dir = os.path.dirname(os.path.dirname(BOFS.__file__))
        current_pythonpath = os.environ.get('PYTHONPATH', '')
        if bofs_parent_dir not in current_pythonpath:
            if current_pythonpath:
                os.environ['PYTHONPATH'] = bofs_parent_dir + os.pathsep + current_pythonpath
            else:
                os.environ['PYTHONPATH'] = bofs_parent_dir

    app.run('0.0.0.0', port)


def run_init(args):
    """Run the interactive project initialization wizard."""
    from .init_wizard import run_wizard
    return run_wizard()


def main():
    # Check if the first argument is a subcommand or a config file (backward compat)
    # If it's not a recognized subcommand and not a flag, treat it as 'run <config>'
    subcommands = {'run', 'init'}
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        # If not a subcommand and not a help flag, assume it's a config file for 'run'
        if first_arg not in subcommands and not first_arg.startswith('-'):
            sys.argv.insert(1, 'run')

    parser = argparse.ArgumentParser(
        description="Bride of Frankensystem - A framework for online experiments and surveys"
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # 'run' subparser - runs the BOFS server
    run_parser = subparsers.add_parser(
        'run',
        help='Run a BOFS project',
        description='Start the BOFS server with the specified configuration file.'
    )
    run_parser.add_argument(
        "config",
        help="Name of config file to load."
    )
    run_parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Toggle debug mode, which enables a debugging bar and provides detailed error "
             "messages in the event of an error."
    )
    run_parser.add_argument(
        "--path", "-p",
        action="store",
        help="Specify the working directory."
    )
    run_parser.add_argument(
        "--reloader-off", "-r",
        action="store_true",
        help="If working in debug mode, turn off the auto-reloading feature."
    )
    run_parser.set_defaults(func=run_server)

    # 'init' subparser - creates a new project
    init_parser = subparsers.add_parser(
        'init',
        help='Create a new BOFS project',
        description='Interactive wizard to create a new BOFS project with customizable features.'
    )
    init_parser.set_defaults(func=run_init)

    args = parser.parse_args()

    # If no command was provided, show help
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Call the appropriate function
    args.func(args)
