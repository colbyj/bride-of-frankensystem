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

    for current_path in os.listdir(path):
        if current_path in ["static", "templates"]:  # We definitely don't want these..
            continue

        considered_path = os.path.join(path, current_path)

        if os.path.isdir(considered_path):  # We should try this path..
            for subpath in os.listdir(considered_path):
                if subpath == "views.py":
                    app.load_blueprint("app." + current_path, current_path)
                if subpath == "models.py":
                    app.load_models("app." + current_path)


    """
    if 'BLUEPRINTS' in app.config:
        for bp in app.config['BLUEPRINTS']:
            app.load_blueprint(bp['package'], bp['name'])

            app.load_models(bp['package'])

            app_context = app.app_context()
            app_context.push()

            app.load_init_functions(bp['package'])

            app_context.pop()
    """

    app.load_blueprint('BOFS.default', 'default')
    app.load_models('BOFS.default')

    # Set defaults for USE_LOGO and USE_BREADCRUMBS
    if not 'USE_BREADCRUMBS' in app.config:
        app.config['USE_BREADCRUMBS'] = True

    if not 'USE_LOGO' in app.config:
        app.config['USE_LOGO'] = True

    if not 'LOG_GRID_CLICKS' in app.config:
        app.config['LOG_GRID_CLICKS'] = False

    with app.app_context():
        app.load_questionnaires()

    app.sess.init_app(app)
    app.db.create_all()

    return app
