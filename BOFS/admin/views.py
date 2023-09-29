from flask import Blueprint, render_template, current_app, redirect, g, request, session, url_for, Response
from BOFS.globals import db, questionnaires, page_list
from BOFS.util import fetch_condition_count, display_time
from .util import sqlalchemy_to_json, verify_admin, escape_csv, questionnaire_name_and_tag, condition_num_to_label
import json
from .QuestionnaireResults import *
from datetime import datetime
from os import path, listdir
from sqlalchemy.orm.attributes import InstrumentedAttribute

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

    return dict(
        additionalAdminPages=additionalAdminPages,
        tableNames=tableNames,
        questionnairesLive=questionnairesLive,
        questionnairesLiveUntagged=questionnairesLiveUntagged,
        questionnairesSystem=questionnairesSystem,
        logGridClicks=current_app.config['LOG_GRID_CLICKS'],
        condition_num_to_label=condition_num_to_label
    )


@admin.route("/")
def admin_index():
    return redirect(url_for("admin.admin_login"))


@admin.route("/login", methods=['GET', 'POST'])
def admin_login():
    if session.get('loggedIn', False):
        return redirect(url_for("admin.route_progress"))

    if request.method == 'POST':
        if request.form['password'] != current_app.config['ADMIN_PASSWORD']:
            return render_template("login_admin.html", message="The password you entered is incorrect.")
        else:
            session['loggedIn'] = True
            session.modified = True

        return redirect(url_for("admin.route_progress"))
    else:
        return render_template("login_admin.html")


def fetch_progress():
    pages = current_app.page_list.flat_page_list()

    progress = db.session.query(db.Participant)

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
        group_by(db.Participant.condition).all()

    summary = db.session.query(
        db.func.count(db.Participant.participantID).label('count'),
        db.func.sum(db.cast(db.Participant.is_abandoned, db.Integer)).label('countAbandoned'),
        db.func.sum(db.cast(db.Participant.is_in_progress, db.Integer)).label('countInProgress'),
        db.func.sum(db.cast(db.Participant.finished, db.Integer)).label('countFinished'),
        db.func.min(db.Participant.duration).label('minSeconds'),
        db.func.max(db.Participant.duration).label('maxSeconds'),
        db.func.avg(db.Participant.duration).label('seconds')). \
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


# Builds the base query for exporting values in blueprint-defined tables
# To be used for each entry in the config's EXPORT
def create_export_base_queries(export_dict):
    table = getattr(db, export_dict['table'])

    levels = None
    filter = None
    groupBy = None
    orderBy = None
    having = None

    if 'filter' in export_dict and export_dict['filter'] != '':
        filter = db.text(export_dict['filter'])

    if 'order_by' in export_dict and export_dict['order_by'] != '':
        orderBy = getattr(table, export_dict['order_by'])

    # determine how many columns to add to the export. If group_by is not used, then it's just one column
    if 'group_by' in export_dict and export_dict['group_by'] != '':
        if 'having' in export_dict and export_dict['having'] != '':  # Having can only work if group_by is used.
            having = db.text(export_dict['having'])

        levelsQ = db.session.query()

        if isinstance(export_dict['group_by'], list):
            groupBy = []
            for gb in export_dict['group_by']:
                groupBy.append(getattr(table, gb))
                levelsQ = levelsQ.add_columns(getattr(table, gb))
                levelsQ = levelsQ.group_by(getattr(table, gb))
        else:
            groupBy = getattr(table, export_dict['group_by'])
            levelsQ = levelsQ.add_columns(groupBy)
            levelsQ = levelsQ.group_by(groupBy)

        if orderBy:
            levelsQ = levelsQ.order_by(orderBy)

        if filter is not None:
            levels = levelsQ.filter(filter).all()
        else:
            levels = levelsQ.all()

    # pk = db.inspect(table).primary_key[0]
    baseQuery = db.session.query(table)

    if groupBy:
        if isinstance(groupBy, list):
            for gb in groupBy:
                baseQuery = baseQuery.group_by(getattr(table, 'participantID'), gb)
        else:
            baseQuery = baseQuery.group_by(getattr(table, 'participantID'), groupBy)

        if having is not None:
            baseQuery = baseQuery.having(having)
    else:
        baseQuery = baseQuery.group_by(getattr(table, 'participantID'))

    if orderBy:
        baseQuery = baseQuery.order_by(orderBy)

    if filter is not None:
        baseQuery = baseQuery.filter(filter)

    # Add the fields to the basequery
    for field in export_dict['fields']:
        if hasattr(table, field) and callable(getattr(table, field)):
            continue  # We can't include this python property as part of the query
        baseQuery = baseQuery.add_columns(db.literal_column(export_dict['fields'][field]).label(field))

    return levels, baseQuery


@admin.route("/export")
@admin.route("/export/download", endpoint="route_export_download")
@verify_admin
def route_export():
    unfinishedCount = db.session.query(db.Participant).filter(
        db.Participant.finished == False).count()  # For display only
    missingCount = 0
    innerJoins = db.session.query(db.Participant)  # Participants with complete data
    leftJoins = db.session.query(db.Participant)  # Participants with complete or incomplete data

    includeUnfinished = request.args.get('includeUnfinished', False)
    includeMissing = request.args.get('includeMissing', False)

    qList = page_list.get_questionnaire_list(include_tags=True)

    columns = dict()

    columns['participant'] = [
        "participantID",
        "externalID",
        "condition",
        "duration",
        "finished"
    ]

    calculatedColumns = dict()

    # First loop constructs the query and fetches the column names
    for qNameAndTag in qList:
        qName, qTag = questionnaire_name_and_tag(qNameAndTag)

        # The python class that describes the questionnaire
        questionnaire = questionnaires[qName]

        # Add the questionnaire's table/class to the query...
        qDBC = db.aliased(questionnaires[qName].dbClass, name=qNameAndTag)

        leftJoins = leftJoins.outerjoin(qDBC,
                                        db.and_(
                                            qDBC.participantID == db.Participant.participantID,
                                            qDBC.tag == qTag
                                        )).add_entity(qDBC)

        innerJoins = innerJoins.join(qDBC,
                                     db.and_(
                                         qDBC.participantID == db.Participant.participantID,
                                         qDBC.tag == qTag
                                     )).add_entity(qDBC)

        # attributes = questionnaires[qName].dbClass.__dict__
        # keys = sorted(attributes.keys())

        columns[qNameAndTag] = []
        calculatedColumns[qNameAndTag] = []

        # Make a list of the columns to later construct the CSV header row
        # This could also be done with questionnaire.fields
        for column in questionnaire.fields:
            columns[qNameAndTag].append(column.id)

        # Similarly, make a list of calculated columns to later be part of the CSV header row.
        for column in questionnaire.calcFields:
            calculatedColumns[qNameAndTag].append(column)

    if not includeUnfinished:
        leftJoins = leftJoins.filter(db.Participant.finished == True)
        innerJoins = innerJoins.filter(db.Participant.finished == True)

    leftJoins = leftJoins.group_by(db.Participant.participantID)
    innerJoins = innerJoins.group_by(db.Participant.participantID)

    if includeMissing:
        rows = leftJoins.all()
    else:
        rows = innerJoins.all()

    missingCount = leftJoins.filter(db.Participant.finished == True).count() - innerJoins.count()

    # Repeated measures in other tables...
    customExports = []

    for export in current_app.config['EXPORT']:
        levels, baseQuery = create_export_base_queries(export)
        customExports.append({'options': export, 'base_query': baseQuery, 'levels': levels})

    # Now that the data is loaded, construct the CSV syntax.
    # Starting with the header row...
    columnList = columns['participant']

    # Add questionnaire fields to CSV header
    for qNameAndTag in qList:
        qName, qTag = questionnaire_name_and_tag(qNameAndTag)

        for col in columns[qNameAndTag]:
            if col.startswith(qName + "_"):  # If it's already prefixed, remove it so the code below works
                col = col.replace(qName, "")

            # Prefix the column with the questionnaire name
            if qTag != "":
                col = qName + "_" + qTag + "_" + col
            else:
                col = qName + "_" + col

            columnList.append(col)

        if qTag != "":
            columnList.append(str.format(u"{}_{}_duration", qName, qTag))
        else:
            columnList.append(str.format(u"{}_duration", qName))

        # Add any calculated columns to the CSV header
        for calcCol in calculatedColumns[qNameAndTag]:
            if qTag != "":
                columnList.append(str.format(u"{}_{}_{}", qName, qTag, calcCol))
            else:
                columnList.append(str.format(u"{}_{}", qName, calcCol))

    # For custom exports, add columns based on levels determined by prior query
    for export in customExports:
        if export['levels']:
            for level in export['levels']:
                for field in export['options']['fields']:
                    columnHeader = str.format(u"{}", field)
                    for levelName in level:
                        columnHeader += str.format(u"_{}", str(levelName).replace(" ", "_"))
                    columnList.append(columnHeader)
        else:
            for field in export['options']['fields']:
                columnList.append(str.format(u"{}", field))

    # Finally construct the CSV string.
    csvString = ",".join(columnList) + "\n"  # CSV Header

    # Iterate through each participant's data
    for row in rows:
        csvString += str.format(u"{},{},{},{},{}",
                                row.participantID,
                                row.mTurkID,
                                condition_num_to_label(row.condition),
                                row.duration,
                                row.finished
                                )

        for qNameAndTag in qList:
            qData = getattr(row, qNameAndTag)
            for col in columns[qNameAndTag]:
                if qData:
                    csvString += "," + escape_csv(getattr(qData, col))
                else:
                    csvString += ","

            if not qData:
                csvString += ","
            else:
                csvString += str.format(u",{}", qData.duration())  # Special case for duration

            # See if there are any calculations to include in the export.
            for col in calculatedColumns[qNameAndTag]:
                if qData:
                    csvString += "," + escape_csv(getattr(qData, col)())
                else:
                    csvString += ","

        for export in customExports:
            query = export['base_query']
            query = query.filter(db.literal_column('participantID') == row.participantID)
            customExportData = query.all()  # Running separate queries will get the job done, but be kind of slow with many participants...

            if export['levels']:
                # build dictionary with one row per level...
                customExportRMs = {}

                # Each unique level in the grouping will have one row. Store the relvant row so it's easier to access
                for r in customExportData:
                    classValues = getattr(r, export['options']['table'])
                    groupValue = ""
                    if isinstance(export['options']['group_by'], list):
                        for gb in export['options']['group_by']:
                            groupValue += str(getattr(classValues, gb))
                    else:
                        groupValue = str(getattr(classValues, export['options']['group_by']))
                    customExportRMs[groupValue] = r

                for level in export['levels']:
                    levelName = ""
                    for levelPart in level:
                        levelName += str(levelPart)

                    for field in export['options']['fields']:
                        if not levelName in customExportRMs:
                            csvString += ","
                            break  # Missing data!

                        classValues = getattr(customExportRMs[levelName], export['options']['table'])

                        # The entire table class is added to the query, as well as the individual fields. So try both.
                        # Try class first due to it also having access to python properties.
                        if hasattr(classValues, field):
                            value = getattr(classValues, field)
                        else:
                            value = getattr(customExportRMs[levelName], field)

                        if callable(value):
                            value = value()

                        csvString += "," + escape_csv(value)
            elif len(customExportData) != 0:
                r = customExportData[0]

                for field in export['options']['fields']:
                    classValues = getattr(r, export['options']['table'])

                    if hasattr(classValues, field):
                        value = getattr(classValues, field)
                    else:
                        value = getattr(r, field)

                    if callable(value):
                        value = value()

                    csvString += "," + escape_csv(value)

            else:
                customExport = ""

                for r in customExportData:
                    classValues = getattr(r, export['options']['table'])

        csvString += "\n"

    if request.base_url.endswith("/download"):
        return Response(csvString,
                        mimetype="text/csv",
                        headers={
                            "Content-disposition": "attachment; filename=%s.csv" % (
                                        "export_" + datetime.utcnow().strftime("%Y-%m-%d_%H-%M"))
                        })
    else:
        return render_template("export.html",
                               data=csvString,
                               rowCount=len(rows),
                               unfinishedCount=unfinishedCount,
                               missingCount=missingCount)


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


@admin.route("/preview_questionnaire/<questionnaireName>")
@verify_admin
def route_preview_questionnaire(questionnaireName):
    errors = []

    try:
        f = open(current_app.root_path + '/questionnaires/' + questionnaireName + ".json", 'r')
        jsonData = f.read()
        jsonData = json.loads(jsonData)
    except Exception as e:
        errors = list(e.args)

    tableName = "questionnaire_" + questionnaireName

    if questionnaireName in page_list.get_questionnaire_list():
        try:
            db.session.query(db.metadata.tables[tableName]).first()
        except Exception as e:
            errors.extend(list(e.args))
            if "(OperationalError) no such column:" in e.args[0]:
                errors.append("Click <a href=\"?fix_errors\">here</a> if you would like to try to automatically add "
                              "this column. Alternatively, you can drop the table and it will be recreated.")
            elif "(OperationalError) no such table:" in e.args[0]:
                errors.append("Click <a href=\"?fix_errors\">here</a> if you would like to try to automatically create "
                              "this table. Alternatively, you can restart the server and it will be created.")

        if 'fix_errors' in request.args:
            # Figure out what column it is by parsing errors.
            for e in errors:
                if "(OperationalError) no such column:" in e:
                    e = e.split(tableName + ".")
                    columnName = e[len(e) - 1]
                    dataType = db.metadata.tables[tableName].columns[columnName].type

                    addColumn = db.DDL(str.format("ALTER TABLE {} ADD COLUMN {} {}", tableName, columnName, dataType))
                    db.engine.execute(addColumn)

                    errors.append(str.format(u"{} {} was added to {}. "
                                             u"This error should be gone when you refresh.", columnName, dataType,
                                             tableName))

                if "(OperationalError) no such table:" in e:
                    db.create_all()
                    errors.append(str.format(u"The error should be gone if you refresh."))

    return render_template("preview_questionnaire.html",
                           q=jsonData,
                           errors=errors)


@admin.route("/questionnaire_html/<questionnaireName>")
@verify_admin
def route_questionnaire_html(questionnaireName):
    errors = []

    try:
        f = open(current_app.root_path + '/questionnaires/' + questionnaireName + ".json", 'r')
        jsonData = f.read()
        jsonData = json.loads(jsonData)
    except Exception as e:
        errors = list(e.args)

    return render_template("preview_questionnaire_simple.html", q=jsonData)


@admin.route("/analyze_questionnaire/<questionnaireName>/<tag>")
@admin.route("/analyze_questionnaire/<questionnaireName>")
@verify_admin
def route_analyze_questionnaire(questionnaireName, tag=0):
    questionnaire = questionnaires[questionnaireName]

    gridPlotData = {}
    gridPlotJSVars = []

    numericResults = NumericResults(questionnaire.dbClass, questionnaire.fields, tag)

    for condition, valueDict in list(numericResults.dataDescriptive.items()):
        gpd = {
            'name': condition,
            'type': 'bar',
            'x': [field for (field, descriptives) in list(valueDict.items())],
            'y': [descriptives.mean for (field, descriptives) in list(valueDict.items())],
            'error_y': {
                'type': 'data',
                'visible': True,
                'array': [descriptives.sem for (field, descriptives) in list(valueDict.items())]
            }
        }
        gridPlotData[condition] = json.dumps(gpd)
        gridPlotJSVars.append("gpd_{}".format(condition))

    return render_template("questionnaire_results.html",
                           questionnaireName=questionnaireName,
                           tag=tag,
                           conditionCount=fetch_condition_count(),
                           gridPlotData=gridPlotData,
                           gridPlotJSVars=json.dumps(gridPlotJSVars).replace('"', ''),
                           numericResults=numericResults)


def table_data(tableName):
    rows = None
    try:
        rows = db.session.query(db.metadata.tables[tableName]).all()
    except Exception as e:
        return render_template("table_view.html", data="", datafields="", columns="", errors=list(e.args))

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
