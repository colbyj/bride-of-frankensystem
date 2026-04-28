import os
from flask import Blueprint, render_template, current_app, redirect, g, request, session, url_for, Response, send_file
from .. import BOFSFlask
from ..globals import db, questionnaires, page_list
from ..util import fetch_condition_count, display_time, provide_consent, int_or_0, utcnow_naive
from .util import sqlalchemy_to_json, verify_admin, escape_csv, questionnaire_name_and_tag, condition_num_to_label
from ..services.participant_questionnaire import ParticipantQuestionnaireService
from ..services.data_export import Results
import json
from ..services.admin_stats import AdminStatsService
from ..services.participant import ParticipantService
from datetime import datetime
from os import path, listdir
from shutil import copyfile


current_app: "BOFSFlask"
admin = Blueprint('admin', __name__, template_folder='templates', static_folder='static', url_prefix="/admin")


@admin.context_processor
def inject_template_vars():
    """
    Inject additional variables into the context of templates within this blueprint
    See http://flask.pocoo.org/docs/1.0/templating/#context-processors
    :return:
    """

    if "ADDITIONAL_ADMIN_PAGES" in current_app.config:
        additionalAdminPages = current_app.config['ADDITIONAL_ADMIN_PAGES']
    else:
        additionalAdminPages = None

    tableNames = []
    for t in db.metadata.tables:
        tableNames.append(t)

    questionnairesSystem = []
    questionnairesLive = []

    for q_name in current_app.questionnaires:
        questionnairesSystem.append(q_name)

        if current_app.questionnaires[q_name].is_in_db:
            questionnairesLive.append(q_name)

    questionnairesLive.sort()
    questionnairesSystem.sort()
    tableNames = sorted(tableNames)
    isSqliteDb = current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')


    return dict(
        additionalAdminPages=additionalAdminPages,
        tableNames=tableNames,
        questionnairesLive=questionnairesLive,
        questionnairesSystem=questionnairesSystem,
        logGridClicks=current_app.config['LOG_GRID_CLICKS'],
        isSqliteDb=isSqliteDb,
        condition_num_to_label=condition_num_to_label
    )


@admin.route("/")
def admin_index():
    return redirect(url_for("admin.admin_login"))


@admin.route("/logged_in")
def admin_logged_in():
    return str(not ('loggedIn' not in session or not session['loggedIn']))


@admin.route("/login", methods=['GET', 'POST'])
def admin_login():
    if 'participantID' not in session:
        p = provide_consent(True)  # Ensure that the previewing user is a valid user
        p.excludeFromCount = True
        db.session.commit()

    if session.get('loggedIn', False):
        return redirect(url_for("admin.route_progress"))

    if request.method == 'POST':
        if request.form['password'] != current_app.config['ADMIN_PASSWORD']:
            return render_template("login_admin.html", message="The password you entered is incorrect.")
        else:
            session['loggedIn'] = True
            session.modified = True

        redirect_to = url_for("admin.route_progress")

        try:
            if request.args.get('r') is not None:
                redirect_to = url_for("admin." + request.args.get('r'))
        except:  # Is there a better method here?
            pass

        return redirect(redirect_to)
    else:
        return render_template("login_admin.html")


@admin.route("/progress")
@verify_admin
def route_progress():
    pages, progress = AdminStatsService.fetch_progress()
    summary_groups, summary = AdminStatsService.fetch_progress_summary()

    return render_template("progress.html",
                           pages=pages, progress=progress,
                           summary_groups=summary_groups, summary=summary, display_time=display_time)


@admin.route("/progress_ajax")
@verify_admin
def route_progress_ajax():
    pages, progress = AdminStatsService.fetch_progress()
    return render_template("progress_ajax.html", pages=pages, progress=progress)


@admin.route("/progress_summary_ajax")
@verify_admin
def route_progress_summary_ajax():
    summary_groups, summary = AdminStatsService.fetch_progress_summary()
    return render_template("progress_summary_ajax.html",
                           summary_groups=summary_groups, summary=summary, display_time=display_time)


@admin.route("/condition/<int:condition_num>/toggle", methods=['POST'])
@verify_admin
def route_toggle_condition(condition_num):
    conditions = current_app.config.get('CONDITIONS', [])
    idx = condition_num - 1
    if idx < 0 or idx >= len(conditions):
        return "Invalid condition", 400

    ParticipantService.toggle_condition_enabled(idx)

    summary_groups, summary = AdminStatsService.fetch_progress_summary()
    return render_template("progress_summary_ajax.html",
                           summary_groups=summary_groups, summary=summary, display_time=display_time)


def _question_text_lookup(questionnaire):
    """Build a {field_id: prompt_text} map from a questionnaire's JSON definition.
    Falls back to the field id if no readable prompt is available."""
    lookup = {}
    qjson = getattr(questionnaire, 'json_data', None) or {}

    def grab_text(defn):
        for key in ('q_text', 'text', 'prompt', 'label', 'title'):
            value = defn.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    for q in qjson.get('questions', []):
        # Single-field question
        if 'id' in q:
            lookup[q['id']] = grab_text(q) or q['id']

        # Group of sub-questions (e.g., radio grid)
        if isinstance(q.get('questions'), list):
            for sub in q['questions']:
                if isinstance(sub, dict) and 'id' in sub:
                    lookup[sub['id']] = grab_text(sub) or sub['id']

    return lookup


def _format_response_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value


def _fetch_page_data(participant, page):
    """Return a dict describing the data submitted for this page, or None.
    Currently only handles questionnaire pages."""
    path = page['path']
    if not path.startswith('questionnaire/'):
        return None

    name_and_tag = current_app.page_list.extract_questionnaire_from_path(path, include_tag=True)
    name, tag = questionnaire_name_and_tag(name_and_tag)

    questionnaire = current_app.questionnaires.get(name)
    if questionnaire is None or questionnaire.db_class is None:
        return None

    row = db.session.query(questionnaire.db_class).filter(
        questionnaire.db_class.participantID == participant.participantID,
        questionnaire.db_class.tag == tag,
    ).first()

    if row is None:
        return None

    prompts = _question_text_lookup(questionnaire)
    fields = []
    for column in questionnaire.fetch_fields():
        fields.append({
            'id': column.id,
            'prompt': prompts.get(column.id, column.id),
            'value': _format_response_value(getattr(row, column.id, None)),
        })

    calculated = []
    for calc_name in questionnaire.get_calculated_fields():
        try:
            value = getattr(row, calc_name)()
        except Exception as e:
            value = f"<calculation error: {e}>"
        calculated.append({'id': calc_name, 'value': _format_response_value(value)})

    return {
        'kind': 'questionnaire',
        'name': name,
        'tag': tag,
        'fields': fields,
        'calculated': calculated,
    }


@admin.route("/participant/<int:pid>")
@verify_admin
def route_participant_detail(pid):
    participant = db.session.get(db.Participant, pid)
    if participant is None:
        return render_template("error.html",
                               title="Participant not found",
                               heading="Participant not found",
                               message=f"No participant exists with ID {pid}."), 404

    # Pass 0 (not None) when the participant has no condition assigned —
    # passing None falls back to the admin's session condition, which is wrong.
    pages = current_app.page_list.flat_page_list(condition=participant.condition or 0)
    progress_rows = db.session.query(db.Progress) \
        .filter(db.Progress.participantID == pid).all()
    progress_by_path = {row.path: row for row in progress_rows}

    timeline = []
    for idx, page in enumerate(pages, start=1):
        path = page['path']
        progress = progress_by_path.get(path)
        started_on = progress.startedOn if progress else None
        submitted_on = progress.submittedOn if progress else None

        # Special cases: consent-style entry pages and the end page never get
        # a normal Progress row that reflects the experiment's actual flow.
        # Entry pages run before the participant is recorded in the DB, so no
        # Progress row is created. The end page sets participant.timeEnded but
        # never POSTs, so submittedOn stays NULL.
        if path in ('consent', 'consent_nc', 'create_participant', 'create_participant_nc'):
            started_on = participant.timeStarted
            submitted_on = participant.timeStarted
            status = 'completed'
        elif path == 'end' and participant.finished:
            started_on = started_on or participant.timeEnded
            submitted_on = participant.timeEnded
            status = 'completed'
        elif progress is None:
            status = 'not_reached'
        elif submitted_on is None:
            status = 'in_progress'
        else:
            status = 'completed'

        if started_on and submitted_on and submitted_on > started_on:
            duration_display = display_time((submitted_on - started_on).total_seconds())
        else:
            duration_display = ""

        timeline.append({
            'index': idx,
            'name': page.get('name', path),
            'path': path,
            'started_on': started_on,
            'submitted_on': submitted_on,
            'duration_display': duration_display,
            'status': status,
            'data': _fetch_page_data(participant, page),
        })

    return render_template("participant_detail.html",
                           participant=participant,
                           timeline=timeline,
                           total_pages=len(pages),
                           display_time=display_time)

@admin.post("/update_exclude_from_count")
def route_update_exclude_from_count():
    if 'participantID' not in request.form or 'excludeFromCount' not in request.form:
        return ""

    p = db.session.get(db.Participant, request.form['participantID'])
    p.excludeFromCount = not (request.form['excludeFromCount'] == 'True')
    db.session.commit()

    return Response(status=200, headers={'HX-Trigger': 'excludeChanged'})

@admin.route("/export_item_timing")
@verify_admin
def route_export_item_timing():
    questionnaires = current_app.page_list.get_questionnaire_list(True)
    header = "participantID,mTurkID"
    output = ""

    headerComplete = False

    results = db.session.query(db.Participant).filter(db.Participant.finished == True).all()

    for p in results:
        output += str.format(u"{},\"{}\"", p.participantID, p.mTurkID.strip())

        for qName in questionnaires:
            tag = ""

            if '/' in qName:
                qNameParts = qName.split('/')
                qName = qNameParts[0]
                tag = qNameParts[1]

            q = p.questionnaire(qName, tag)
            logs = p.questionnaire_log(qName, tag)

            qNameFull = qName
            if len(tag) > 0:
                qNameFull = "{}_{}".format(qName, tag)

            for key in sorted(logs.keys()):
                if not headerComplete:
                    header += ",{}_{}".format(qNameFull, key)

                output += ",{}".format(logs[key])

        output += "\n"
        headerComplete = True

    return render_template("export_csv.html", data=str.format(u"{}\n{}", header, output))


@admin.route("/export")
@admin.route("/export/download", endpoint="route_export_download")
@verify_admin
def route_export():
    unfinished_count = db.session.query(db.Participant). \
        filter(db.Participant.finished == False).count()  # For display only
    excluded_count = db.session.query(db.Participant). \
        filter(db.Participant.excludeFromCount == True).count()  # For display only

    results = Results(Results.build_filter_from_args(request.args))
    df = results.build_data_frame()


    if request.base_url.endswith("/download"):
        return Response(df.to_csv(),
                        mimetype="text/csv",
                        headers={
                            "Content-disposition": "attachment; filename=%s.csv" %
                                                   ("export_" + utcnow_naive().strftime("%Y-%m-%d_%H-%M"))
                        })
    else:
        return render_template("export.html",
                               data_table=df.to_html(index=False, classes="table table-striped border", justify="left"),
                               rowCount=len(results.export_data),
                               unfinishedCount=unfinished_count,
                               excludedCount=excluded_count)


@admin.route("/results")
@verify_admin
def route_results():
    cache_path = os.path.join(current_app.root_path, 'cached_results.json')
    results, df, summary_stats = Results.calculate_results(cache_path)

    return render_template("results.html", summary_stats=summary_stats)


@admin.route("/results_boxplot/<path:field_name>")
@verify_admin
def route_results_boxplot(field_name: str):
    cache_path = os.path.join(current_app.root_path, 'cached_results.json')
    results, df, summary_stats = Results.calculate_results(cache_path)

    unique_conditions = df['condition'].unique().tolist()
    unique_conditions.sort()
    plot_data = []

    for condition in unique_conditions:
        df_part = df.loc[df.condition == condition]
        #count = df_part.count()

        data = {
            "y": df_part[field_name].to_list(),
            #"x": [condition] * count,
            "name": str(condition),
            "type": "box",
            "boxpoints": "Outliers"
        }
        plot_data.append(data)

    return render_template("results_boxplot.html", field_name=field_name, plot_data=plot_data)


@admin.route("/preview_procedure", methods=["GET", "POST"])
@verify_admin
def route_preview_procedure():
    #questionnaires = current_app.page_list.parse_list_into_procedure()
    mermaid_string = current_app.page_list.to_mermaid()

    #try:
    #    f = open(current_app.get_questionnaire_path(questionnaireName), 'r')
    #    json_data = f.read()
    #    json_data = json.loads(json_data)
    #    f.close()
    #
    #except Exception as e:
    #    errors = list(e.args)
    #
    #return JSONQuestionnaire.render_unloaded_questionnaire(json_data, "preview_questionnaire.html", errors=errors)

    return render_template("procedure.html", mermaid_string=mermaid_string)

@admin.route("/preview_questionnaire/<questionnaireName>", methods=["GET", "POST"])
@verify_admin
def route_preview_questionnaire(questionnaireName):
    if request.method == 'POST' and 'condition' in request.form:
        session['condition'] = int_or_0(request.form['condition'])

        p = db.session.get(db.Participant, session['participantID'])
        p.condition = session['condition']
        db.session.commit()

    errors = []
    json_data = None

    try:
        f = open(current_app.get_questionnaire_path(questionnaireName), 'r')
        json_data = f.read()
        json_data = json.loads(json_data)
        f.close()

    except Exception as e:
        errors = list(e.args)

    return ParticipantQuestionnaireService.render_unloaded_questionnaire(json_data, "preview_questionnaire.html", errors=errors)


@admin.route("/questionnaire_html/<questionnaireName>")
@verify_admin
def route_questionnaire_html(questionnaireName):
    errors = []
    json_data = None

    try:
        f = open(current_app.get_questionnaire_path(questionnaireName), 'r')
        json_data = f.read()
        json_data = json.loads(json_data)
        f.close()
    except Exception as e:
        errors = list(e.args)

    return ParticipantQuestionnaireService.render_unloaded_questionnaire(json_data, "preview_questionnaire_simple.html", errors=errors)


def table_data(tableName):
    rows = db.session.query(db.metadata.tables[tableName]).all()

    columns = []

    for c in db.metadata.tables[tableName].columns:
        type = str(c.type)
        if type.startswith("VARCHAR") or type.startswith("TEXT"):
            type = u"string"

        column = {'name': c.description, 'type': type.lower()}

        columns.append(column)

    return columns, rows


@admin.route("/table_view/<tableName>")
@verify_admin
def route_table_view(tableName):
    columns, rows = table_data(tableName)
    return render_template("table_view.html", tableName=tableName, rows=rows, columns=columns)


@admin.route("/table_ajax/<tableName>")
@verify_admin
def route_table_ajax(tableName):
    columns, rows = table_data(tableName)
    return render_template("table_ajax.html", rows=rows, columns=columns)


@admin.route("/table_csv/<tableName>")
@verify_admin
def route_table_csv(tableName):
    columns, rows = table_data(tableName)

    csv = ""
    headers = [c['name'] for c in columns]
    csv += ",".join(headers) + "\n"

    for row in rows:
        csv += ",".join([escape_csv(row[i]) for i, c in enumerate(columns)]) + "\n"

    return Response(csv,
                    mimetype="text/csv",
                    headers={
                        "Content-disposition": "attachment; filename=%s.csv" % (
                                    tableName + "_" + utcnow_naive().strftime("%Y-%m-%d"))
                    })


@admin.route("/database_download")
@verify_admin
def route_database_download():
    if not current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'):
        return "Not using a SQLite database."

    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    # TODO: Do I need to do something special if the database is being written to by users?
    return send_file(db_uri, as_attachment=True)


@admin.route("/database_delete", methods=['GET', 'POST'])
@verify_admin
def route_database_delete():
    if not current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'):
        return "Not using a SQLite database."

    if request.method == 'POST':
        if request.form['password'] != current_app.config['ADMIN_PASSWORD']:
            return render_template("database_delete.html", message="The password you entered is incorrect.")
        else:
            db_uri = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            copyfile(db_uri, db_uri.replace('.db', '') + "_" + utcnow_naive().strftime("%Y%m%d_%H%M%S") + ".db")  # Make a copy of the db, just in case we didn't truly want to delete everything.

            # now delete everything from the database
            for tbl in reversed(db.metadata.sorted_tables):
                db.session.query(tbl).delete()
            db.session.commit()

        return redirect(url_for("admin.route_progress"))

    return render_template("database_delete.html")

    #db_uri = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    #return send_file(db_uri, as_attachment=True)


