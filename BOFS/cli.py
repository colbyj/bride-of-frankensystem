import os
import argparse
from .create_app import create_app


def main():
    parser = argparse.ArgumentParser(description="Bride of Frankensystem")
    parser.add_argument("config",
                        help="Name of config file to load.")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Toggle debug mode, which enables a debugging bar and provides detailed error " \
                             + "messages in the event of an error.")
    parser.add_argument("--path", "-p", action="store",
                        help="Specify the working directory.")
    parser.add_argument("--reloader-off", "-r", action="store_true",
                        help="If working in debug mode, turn off the auto-reloading feature.")

    args = parser.parse_args()

    if args.path:
        path = args.path
    else:
        # Set the path based on the path of the config file.
        path = os.path.dirname(os.path.abspath(args.config))
        args.config = os.path.basename(args.config)

    app = create_app(path, args.config, args.debug, args.reloader_off)
    port = 5000  # Default to port 5000 if it's not set.

    if "PORT" in app.config:
        port = app.config["PORT"]

    app.run('0.0.0.0', port)
