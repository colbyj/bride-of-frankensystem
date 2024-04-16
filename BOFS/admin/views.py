import sqlalchemy
from flask import Blueprint, render_template, current_app, redirect, g, request, session, url_for, Response, send_file
from BOFS.globals import db, questionnaires, page_list
from BOFS.util import fetch_condition_count, display_time, provide_consent, int_or_0
from .util import sqlalchemy_to_json, verify_admin, escape_csv, questionnaire_name_and_tag, condition_num_to_label
from .export_helpers import *
import json
from .QuestionnaireResults import *
from datetime import datetime
from os import path, listdir
from shutil import copyfile

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

    if path.exists(current_app.root_path + "/questionnaires"):
        for q in listdir(current_app.root_path + "/questionnaires"):
            if q.endswith(".json"):
                questionnairesSystem.append(q.replace(".json", ""))

    tableNames = sorted(tableNames)
    questionnairesLive = current_app.page_list.get_questionnaire_list(True)
    questionnairesLiveUntagged = sorted(current_app.page_list.get_questionnaire_list())
    questionnairesSystem = sorted(questionnairesSystem)
    isSqliteDb = current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')


    return dict(
        additionalAdminPages=additionalAdminPages,
        tableNames=tableNames,
        questionnairesLive=questionnairesLive,
        questionnairesLiveUntagged=questionnairesLiveUntagged,
        questionnairesSystem=questionnairesSystem,
        logGridClicks=current_app.config['LOG_GRID_CLICKS'],
        isSqliteDb=isSqliteDb,
        condition_num_to_label=condition_num_to_label
    )


@admin.route("/")
def admin_index():
    return redirect(url_for("admin.admin_login"))


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


def fetch_progress():
    pages = current_app.page_list.flat_page_list()
    progress = db.session.query(db.Participant).filter(db.Participant.isCrawler == False)

    for page in pages:
        if page['path'] in ["end", "consent"]:  # Don't show end page, use Participant.finished instead.
            pages.remove(page)
            continue

    for page in pages:
        pp = db.aliased(db.Progress, name=page['path'])
        progress = progress.outerjoin(pp, db.and_(
            pp.participantID == db.Participant.participantID,
            pp.path == page['path']
        )).add_entity(
            pp
        )

    progress = progress.all()
    return pages, progress


def fetch_progress_summary():
    summary_groups = db.session.query(
        db.Participant.condition,
        db.func.count(db.Participant.participantID).label('count'),
        db.func.sum(db.cast(db.Participant.is_abandoned, db.Integer)).label('countAbandoned'),
        db.func.sum(db.cast(db.Participant.is_in_progress, db.Integer)).label('countInProgress'),
        db.func.sum(db.cast(db.Participant.finished, db.Integer)).label('countFinished'),
        db.func.avg(db.Participant.duration).label('minutes')). \
        filter(db.or_(~db.Participant.excludeFromCount, db.Participant.excludeFromCount == None)). \
        group_by(db.Participant.condition).all()

    summary = db.session.query(
        db.func.count(db.Participant.participantID).label('count'),
        db.func.sum(db.cast(db.Participant.is_abandoned, db.Integer)).label('countAbandoned'),
        db.func.sum(db.cast(db.Participant.is_in_progress, db.Integer)).label('countInProgress'),
        db.func.sum(db.cast(db.Participant.finished, db.Integer)).label('countFinished'),
        db.func.min(db.Participant.duration).label('minSeconds'),
        db.func.max(db.Participant.duration).label('maxSeconds'),
        db.func.avg(db.Participant.duration).label('seconds')). \
        filter(db.or_(~db.Participant.excludeFromCount, db.Participant.excludeFromCount == None)). \
        one()

    return summary_groups, summary


@admin.route("/progress")
@verify_admin
def route_progress():
    pages, progress = fetch_progress()
    summary_groups, summary = fetch_progress_summary()

    return render_template("progress.html",
                           pages=pages, progress=progress,
                           summary_groups=summary_groups, summary=summary, display_time=display_time)


@admin.route("/progress_ajax")
@verify_admin
def route_progress_ajax():
    pages, progress = fetch_progress()
    return render_template("progress_ajax.html", pages=pages, progress=progress)


@admin.route("/progress_summary_ajax")
@verify_admin
def route_progress_summary_ajax():
    summary_groups, summary = fetch_progress_summary()
    return render_template("progress_summary_ajax.html",
                           summary_groups=summary_groups, summary=summary, display_time=display_time)

@admin.post("/update_exclude_from_count")
def route_update_exclude_from_count():
    if 'participantID' not in request.form or 'excludeFromCount' not in request.form:
        return ""

    p = db.session.query(db.Participant).get(request.form['participantID'])
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

    include_unfinished = request.args.get('includeUnfinished', False)
    include_missing = request.args.get('includeMissing', True)
    include_excluded = request.args.get('includeExcluded', False)

    column_list = []
    export_data = {}

    query = add_participants_to_export(column_list, export_data, include_unfinished, include_excluded)
    add_questionnaires_to_export(column_list, export_data, query, include_missing)
    add_custom_exports_to_export(column_list, export_data, query, include_missing)

    csv_string = build_export_csv(column_list, export_data)

    if request.base_url.endswith("/download"):
        return Response(csv_string,
                        mimetype="text/csv",
                        headers={
                            "Content-disposition": "attachment; filename=%s.csv" %
                                                   ("export_" + datetime.utcnow().strftime("%Y-%m-%d_%H-%M"))
                        })
    else:
        return render_template("export.html",
                               data=csv_string,
                               rowCount=len(export_data),
                               unfinishedCount=unfinished_count,
                               excludedCount=excluded_count)


@admin.route("/results")
@verify_admin
def route_results():
    qList = page_list.get_questionnaire_list(include_tags=True)
    results = {}

    for qNameAndTag in qList:
        qName, qTag = questionnaire_name_and_tag(qNameAndTag)

        qResults = QuestionnaireResults(questionnaires[qName], qTag)
        qResults.run_query()
        qResults.calc_descriptives()

        results[qNameAndTag] = qResults

    return render_template("results.html", results=results)


@admin.route("/preview_questionnaire/<questionnaireName>", methods=["GET", "POST"])
@verify_admin
def route_preview_questionnaire(questionnaireName):
    if request.method == 'POST' and 'condition' in request.form:
        session['condition'] = int_or_0(request.form['condition'])

        p = db.session.query(db.Participant).get(session['participantID'])
        p.condition = session['condition']

        db.session.commit()

    errors = []

    try:
        f = open(current_app.get_questionnaire_path(questionnaireName), 'r')
        json_data = f.read()
        json_data = json.loads(json_data)
        f.close()
    except Exception as e:
        errors = list(e.args)

    table_name = "questionnaire_" + questionnaireName

    return render_template("preview_questionnaire.html",
                           q=json_data,
                           errors=errors)


@admin.route("/questionnaire_html/<questionnaireName>")
@verify_admin
def route_questionnaire_html(questionnaireName):
    errors = []

    try:
        f = open(current_app.get_questionnaire_path(questionnaireName), 'r')
        json_data = f.read()
        json_data = json.loads(json_data)
        f.close()
    except Exception as e:
        errors = list(e.args)

    return render_template("preview_questionnaire_simple.html", q=json_data)


#@admin.route("/analyze_questionnaire/<questionnaireName>/<tag>")
#@admin.route("/analyze_questionnaire/<questionnaireName>")
#@verify_admin
#def route_analyze_questionnaire(questionnaireName, tag=0):
#    questionnaire = questionnaires[questionnaireName]
#
#    gridPlotData = {}
#    gridPlotJSVars = []
#
#    numericResults = NumericResults(questionnaire.dbClass, questionnaire.fields, tag)
#
#    for condition, valueDict in list(numericResults.dataDescriptive.items()):
#        gpd = {
#            'name': condition,
#            'type': 'bar',
#            'x': [field for (field, descriptives) in list(valueDict.items())],
#            'y': [descriptives.mean for (field, descriptives) in list(valueDict.items())],
#            'error_y': {
#                'type': 'data',
#                'visible': True,
#                'array': [descriptives.sem for (field, descriptives) in list(valueDict.items())]
#            }
#        }
#        gridPlotData[condition] = json.dumps(gpd)
#        gridPlotJSVars.append("gpd_{}".format(condition))
#
#    return render_template("questionnaire_results.html",
#                           questionnaireName=questionnaireName,
#                           tag=tag,
#                           conditionCount=fetch_condition_count(),
#                           gridPlotData=gridPlotData,
#                           gridPlotJSVars=json.dumps(gridPlotJSVars).replace('"', ''),
#                           numericResults=numericResults)


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
                                    tableName + "_" + datetime.utcnow().strftime("%Y-%m-%d"))
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
            copyfile(db_uri, db_uri.replace('.db', '') + "_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S") + ".db")  # Make a copy of the db, just in case we didn't truly want to delete everything.

            # now delete everything from the database
            for tbl in reversed(db.metadata.sorted_tables):
                db.session.query(tbl).delete()
            db.session.commit()

        return redirect(url_for("admin.route_progress"))

    return render_template("database_delete.html")

    #db_uri = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    #return send_file(db_uri, as_attachment=True)


