import os
import sys
from .BOFSFlask import BOFSFlask
from .admin.util import check_and_add_column


def create_app(path, config_name, debug=False, reloader_off=False):
    os.chdir(path)  # Set the current working directory to the specified path
    sys.path.append(path)  # Ensure BOFS can find the blueprints properly

    app = BOFSFlask(__name__,
                    config_name=config_name,
                    root_path=path,
                    run_with_debugging=debug,
                    run_with_reloader_off=reloader_off)

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

        if os.path.isdir(considered_path) and not current_path.startswith("."):  # We should try this path.
            found_views = False

            for subpath in os.listdir(considered_path):
                if subpath == "views.py":
                    app.load_blueprint(current_path, current_path, False)
                    found_views = True
                if subpath == "models.py":
                    app.load_models(current_path)

            if not found_views:  # If no views, then create a blank blueprint, so we can still search the templates folder, etc.
                app.load_empty_blueprint(current_path)

    app.load_blueprint('BOFS.default', 'default')

    with app.app_context():
        if not app.questionnaire_list_is_safe():
            print("Error! The same questionnaire was specified twice. Please add a tag to your questionnaire if this "
                  "was intentional.")
            return

        app.load_questionnaires()
        app.load_tables()
        app.db.create_all()

        # Check to see if all the columns are there
        # These are columns added to newer versions of BOFS
        check_and_add_column('participant', 'excludeFromCount', 'BOOLEAN', 0)
        check_and_add_column('participant', 'notes', 'TEXT', '')

        if check_and_add_column('participant', 'isCrawler', 'BOOLEAN', 0):
            # If this column wasn't in there, then also check all prior participants' useragent.
            participants = app.db.session.query(app.db.Participant).all()
            for participant in participants:
                participant.check_useragent_for_crawler()
            app.db.session.commit()
            print("Checking participants for web scrapers.")

        # Now user-defined questionnaires
        for q_key in app.questionnaires:
            q = app.questionnaires[q_key]
            q_fields = q.fetch_fields()
            table_name = q.db_class.__tablename__

            for field in q_fields:
                if check_and_add_column(table_name, field.id, field.get_type_ddl(), field.default):
                    print(f"Added new column to {table_name}: {field.id}")

        for t_key in app.tables:
            t = app.tables[t_key]
            columns = t.get_columns()
            table_name = t.db_class.__tablename__

            for column in columns:
                if check_and_add_column(table_name, column.name, column.get_type_ddl(), column.default):
                    print(f"Added new column to {t_key}: {column.name}")

    return app
