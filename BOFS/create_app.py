from __future__ import absolute_import
import os
import imp
from .BOFSFlask import BOFSFlask


def create_app(path, config_name='default.cfg', debug=False):
    app = BOFSFlask(__name__, config_name=config_name, root_path=path)
    app.load_config(config_name, silent=False)
    app.debug = debug

    if 'USE_ADMIN' not in app.config or app.config['USE_ADMIN'] is True:
        app.load_blueprint('BOFS.admin', 'admin')

    # Set defaults for some config options
    if not 'USE_BREADCRUMBS' in app.config:
        app.config['USE_BREADCRUMBS'] = True

    if not 'USE_LOGO' in app.config:
        app.config['USE_LOGO'] = True

    if not 'LOG_GRID_CLICKS' in app.config:
        app.config['LOG_GRID_CLICKS'] = False

    if not 'ADDITIONAL_ADMIN_PAGES' in app.config:
        app.config['ADDITIONAL_ADMIN_PAGES'] = []

    if not 'EXPORT' in app.config:
        app.config['EXPORT'] = []

    if not 'ALLOW_RETAKES' in app.config:
        app.config['ALLOW_RETAKES'] = False

    for current_path in os.listdir(path):
        if current_path in ["static", "templates"]:  # We're inside a blueprint. Unlikely that there is another one here...
            continue

        considered_path = os.path.join(path, current_path)

        if os.path.isdir(considered_path):  # We should try this path..
            for subpath in os.listdir(considered_path):
                if subpath == "views.py":
                    app.load_blueprint("app." + current_path, current_path, False)
                if subpath == "models.py":
                    app.load_models("app." + current_path)

    app.load_blueprint('BOFS.default', 'default')

    with app.app_context():
        app.load_questionnaires()

    app.db.create_all()

    return app
