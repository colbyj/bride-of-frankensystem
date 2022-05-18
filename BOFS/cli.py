import os
import argparse
from .create_app import create_app


def main():
    parser = argparse.ArgumentParser(description="Bride of Frankensysten")
    parser.add_argument("config", help="Name of config file to load.")
    parser.add_argument("--debug", "-d", action="store_true", help="Toggle debug mode, which enables a debugging bar and provides detailed error messagees in the event of an error.")
    parser.add_argument("--path", "-p", action="store", help="Specify the working directory.")

    args = parser.parse_args()

    if args.path:
        path = args.path
    else:
        path = os.getcwd()

    app = create_app(path, args.config)

    app.debug = args.debug

    port = 5000  # Default to port 5000 if it's not set.

    if "PORT" in app.config:
        port = app.config["PORT"]

    app.run('0.0.0.0', app.config["PORT"])