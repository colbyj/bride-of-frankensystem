import os
import sys
from .BOFSFlask import BOFSFlask


def create_app(path, config_name, debug=False):
    os.chdir(path)  # Set the current working directory to the specified path
    sys.path.append(path)  # Ensure BOFS can find the blueprints properly

    app = BOFSFlask(__name__, config_name=config_name, root_path=path)
    app.load_config(config_name, silent=False)
    app.debug = debug

    if 'USE_ADMIN' not in app.config or app.config['USE_ADMIN'] is True:
        app.load_blueprint('BOFS.admin', 'admin')

    # Set defaults for some config options
    if 'USE_BREADCRUMBS' not in app.config:
        app.config['USE_BREADCRUMBS'] = True

    if 'USE_LOGO' not in app.config:
        app.config['USE_LOGO'] = True

    if 'LOG_GRID_CLICKS' not in app.config:
        app.config['LOG_GRID_CLICKS'] = False

    if 'ADDITIONAL_ADMIN_PAGES' not in app.config:
        app.config['ADDITIONAL_ADMIN_PAGES'] = []

    if 'EXPORT' not in app.config:
        app.config['EXPORT'] = []

    if 'ALLOW_RETAKES' not in app.config:
        app.config['ALLOW_RETAKES'] = False

    if 'RETRIEVE_SESSIONS' not in app.config:
        app.config['RETRIEVE_SESSIONS'] = True

    if 'EXTERNAL_ID_LABEL' not in app.config:
        app.config['EXTERNAL_ID_LABEL'] = "Mechanical Turk Worker ID"

    if 'EXTERNAL_ID_PROMPT' not in app.config:
        app.config['EXTERNAL_ID_PROMPT'] = "Please enter your MTurk Worker ID. You can find this on your MTurk dashboard."

    if 'GENERATE_COMPLETION_CODE' not in app.config:
        app.config['GENERATE_COMPLETION_CODE'] = True

    if 'STATIC_COMPLETION_CODE' not in app.config:
        app.config['STATIC_COMPLETION_CODE'] = None

    if 'COMPLETION_CODE_MESSAGE' not in app.config:
        app.config['COMPLETION_CODE_MESSAGE'] = "Please copy and paste this code into the MTurk form:"

    if 'OUTGOING_URL' not in app.config:
        app.config['OUTGOING_URL'] = None

    if 'ABANDONED_MINUTES' not in app.config:
        app.config['ABANDONED_MINUTES'] = 5

    if 'COUNTS_INCLUDE_ABANDONED' not in app.config:
        app.config['COUNTS_INCLUDE_ABANDONED'] = False

    if 'CONDITIONS' not in app.config:
        app.config['CONDITIONS'] = []

    for current_path in os.listdir(path):
        if current_path in ["static", "templates"]:  # We're inside a blueprint. Unlikely that there is another one here...
            continue

        considered_path = os.path.join(path, current_path)

        if os.path.isdir(considered_path):  # We should try this path..
            for subpath in os.listdir(considered_path):
                if subpath == "views.py":
                    app.load_blueprint(current_path, current_path, False)
                if subpath == "models.py":
                    app.load_models(current_path)

    app.load_blueprint('BOFS.default', 'default')

    with app.app_context():
        if not app.questionnaire_list_is_safe():
            print("Error! The same questionnaire was specified twice. Please add a tag to your questionnaire if this "
                  "was intentional.")
            return
        app.load_questionnaires()
        app.load_tables()
        app.db.create_all()

    return app
