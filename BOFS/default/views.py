from flask import Blueprint, render_template, current_app, request, make_response
from urllib.parse import urlsplit
import traceback
from BOFS.JSONTable import JSONTable
from BOFS.util import *
from BOFS.globals import db, referrer, page_list, questionnaires, tables
from BOFS.BOFSSession import BOFSSessionInterface, BOFSSession


default = Blueprint('default', __name__)


@default.route("/")
@verify_correct_page
def route_index():
    return "You shouldn't be able to see this."


@default.route("/consent", methods=['POST', 'GET'])
@verify_correct_page
def route_consent():
    """
    ``/consent``

    This shows a consent form. Upon submission, the participant entry is created in the database, they
    are assigned a condition, and the session variables are set.
    This is typically the first page you will use in ``PAGE_LIST``. If not, use one of

    * ``/consent_nc``
    * ``/create_participant``
    * ``/create_participant_nc``
    """
    if request.method == 'POST':
        if 'email' in request.form and request.form['email'] != '':
            # We caught someone with our honeypot.
            return render_template("consent.html")

        provide_consent(True)
        return redirect("/redirect_from_page/consent")

    return render_template("consent.html")


# Sets a participant's condition to 0 instead of assigning it as normal
@default.route("/consent_nc", methods=['POST', 'GET'])
@verify_correct_page
def route_consent_nc():
    """
    ``/consent_nc``

    This acts just like ``/consent``, except it does not assign the user a condition (defaults to 0).
    """
    if request.method == 'POST':
        provide_consent(False)
        return redirect("/redirect_from_page/consent_nc")
    return render_template("consent.html")


# Use this route in place of /consent, if you want to bypass the consent form.
@default.route("/create_participant")
def route_create_participant():
    """
    ``/create_participant``

    This creates the participant in the database and sets up the session variables. Use if you don't need to
    show a consent form.
    """
    provide_consent(True, False)
    return redirect("/redirect_from_page/create_participant")


# Use this route in place of /consent_nc, if you want to bypass the consent form without assigning a condition.
@default.route("/create_participant_nc")
def route_create_participant_nc():
    """
    ``/create_participant_nc``

    This creates the participant in the database and sets up the session variables. Use if you don't need to
    show a consent form.

    This does not assign the participant a condition (defaults to 0)
    and so could be used in conjunction with ``/assign_condition``.
    """
    provide_consent(False, False)
    return redirect("/redirect_from_page/create_participant_nc")


@default.route("/assign_condition")
@verify_session_valid
@verify_correct_page
def route_assign_condition():
    """
    ``/assign_condition``

    Typically, conditions are assigned upon consent. Use this page if you want to assign a condition later on in
    the experiment. This might be used, for example, after several initial questionnaires, so that participants
    who fail to actually attempt the task don't end up getting assigned a condition.

    If you used ``/consent_nc`` or ``/create_participant_nc``, then you will need to use this to assign them to a
    condition other than 0.
    """
    p = db.session.query(db.Participant).get(session['participantID'])
    p.assign_condition()
    db.session.commit()

    session['condition'] = p.condition

    return redirect("/redirect_from_page/assign_condition")


@default.route("/startMTurk", methods=['POST', 'GET'])  # Deprecated
@default.route("/start_mturk", methods=['POST', 'GET'])
@default.route("/external_id", methods=['POST', 'GET'])
@verify_correct_page
def route_external_id():
    """
    ``/external_id`` or (for backwards compatibility) ``/startMTurk`` or ``/start_mturk``

    If we are using a platform where the user has a unique (and anonymous) ID associated with their account,
    then you can use this page to request that ID. This is set up to work with Mechanical Turk, but the
    template can be overwritten to request different types of ID.
    :return:
    """
    if request.method == 'POST':
        p = db.Participant.query.get(session['participantID'])
        p.mTurkID = str(request.form['mTurkID']).strip()

        session['mTurkID'] = p.mTurkID

        # Don't try to load any past attempts if this config option is set
        if not current_app.config['RETRIEVE_SESSIONS']:
            return redirect(join_urls('/redirect_from_page', request.path))

        sessionFromMTurkID = db.session.query(db.SessionStore).\
            filter(db.SessionStore.mTurkID == p.mTurkID).\
            order_by(db.desc(db.SessionStore.createdOn)).all()

        allowRetakes = current_app.config['ALLOW_RETAKES']

        # This person has tried the task before and didn't finish. Let's load their information.
        # This will leave an orphaned participant in the DB (they will load up and use their old participantID).
        # If they had previously finished an attempt, then let them start over.
        if sessionFromMTurkID and len(sessionFromMTurkID) > 0:
            pFromMTurkID = db.session.query(db.Participant). \
                filter(
                    db.Participant.mTurkID == p.mTurkID,
                    db.Participant.participantID == sessionFromMTurkID[0].participantID
                )

            if allowRetakes:
                # If allow retakes is True, then don't try to re-load data from past attempts that were completed.
                pFromMTurkID = pFromMTurkID.filter(db.Participant.finished != True, db.Participant.participantID != session['participantID'])

            pFromMTurkID = pFromMTurkID.all()

            # Load their old session
            if pFromMTurkID and len(pFromMTurkID) > 0:
                dictData = BOFSSessionInterface.serializer.loads(sessionFromMTurkID[0].data)
                for key in dictData.keys():
                    session[key] = dictData[key]

                # Ensure that if conditions are used, their incomplete attempt doesn't skew the counts.
                p.condition = None
                db.session.commit()

                # Their condition will be loaded from the session data already. This is extra insurance.
                for pPastAttempt in pFromMTurkID:
                    # Find the attempt that has the actual condition set (second attempts onward will have condition 0)
                    if pPastAttempt.condition != 0 and pPastAttempt.condition is not None:
                        session['condition'] = pPastAttempt.condition

                # Redirect them to where they should actually be, only if that location is not going to put them in a weird loop.
                # TODO: Dynamically create a list of pages to avoid redirecting to from PAGE_LIST
                if 'currentUrl' in dictData and session['currentUrl'] not in ('startMTurk', 'start_mturk', 'external_id', 'consent'):
                    return redirect(session['currentUrl'])

        return redirect(join_urls('/redirect_from_page', request.path))

    mTurkID = None
    if 'mTurkID' in session and len(session['mTurkID']) > 0:
        mTurkID = session['mTurkID']

    return render_template('external_id.html', mTurkID=mTurkID)


@default.route("/table/<tableName>", methods=['POST', 'GET'])
def route_table(tableName):
    """
    ``/table/<tableName>``

    Provides a simple API to get data from a table (via GET) or add data to a table (via POST).

    :param tableName: The name of the table, as it is in /app/tables (without the .json)
    :return: the return value is either ``JSONTable.handle_post()`` or ``JSONTable.handle_get()`` depending on the request type.
    """
    t: "JSONTable" = tables[tableName]

    if request.method == 'POST':
        return t.handle_post()

    return t.handle_get()


@default.route("/questionnaire/<questionnaireName>", methods=['POST', 'GET'])
@default.route("/questionnaire/<questionnaireName>/<tag>", methods=['POST', 'GET'])
@verify_correct_page
def route_questionnaire(questionnaireName, tag=""):
    """
    ``/questionnaire/<questionnaireName>`` or ``/questionnaire/<questionnaireName>/<tag>``

    Render a questionnaire with the specified name. The questionnaire should be defined as a JSON file (with a .json
    file extension) in the ``/questionnaire`` directory.

    If the same questionnaire is going to be used twice, then use the URL that includes the <tag>, this allows you to
    define a name associated with that instance of the questionnaire. For example, "before" and "after" or "1" and "2".

    :param questionnaireName: The name of the json file (without the .json extension).
    :param tag: If the same questionnaire is to be displayed more than once, provide it with a
                unique tag (e.g., "before" or "after" or "1")
    """
    q = questionnaires[questionnaireName]

    if request.method == 'POST':
        q.handle_questionnaire(tag)

        return redirect(join_urls('/redirect_from_page', request.path))

    return render_template('questionnaire.html',
                           tag=tag,
                           q=q.json_data,
                           timeStarted=datetime.datetime.utcnow())


@default.route("/questionnaire_question/<questionType>", methods=['POST'])
def route_questionnaire_question(questionType: str):
    """
    ``/questionnaire_question/<questionType>``

    Render a specific question type for the questionnaire. Only accepts POST requests.
    Data posted to this route must be a JSON object of the question data.
    """
    if 'participantID' not in session:
        raise Exception('Error: No participantID in session. Did you forget /consent or /create_participant, etc.?')

    participant = db.Participant.query.get(session['participantID'])

    try:
        return render_template(f'questions/{questionType}.html',
                               question=request.json,
                               participant=participant)
    except Exception as ex:
        if current_app.run_with_debugging:
            debugging_info = str(ex) + "<p><pre>" + str(traceback.format_exc()) + "</pre>"
        else:
            debugging_info = str(ex)

        return f"Exception in <b>{questionType}.html</b>: {debugging_info}"


@default.route("/redirect_previous_page")
def route_redirect_previous_page():
    """
    ``/redirect_previous_page``

    Sends a user to the previous page. This is intended primarily for debugging purposes.
    """
    session['currentUrl'] = page_list.previous_path(session['currentUrl'])
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/redirect_next_page")
def route_redirect_next_page():
    """
    ``/redirect_next_page``

    This is the preferred way of sending a user to the next page.
    """
    if not request is None and not request.referrer is None:
        parsed = urlsplit(request.referrer)
        current_page = parsed.path
        #currentPage = str.replace(str(request.referrer), request.host_url, "")

    else:
        current_page = session['currentUrl']

    if current_page == "end":
        return redirect(current_app.config["APPLICATION_ROOT"] + "/end")

    session['currentUrl'] = page_list.next_path(current_page)
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/redirect_from_page/<path:page>")
def route_redirect_from_page(page):
    """
    ``/redirect_from_page/<path:page>``

    Redirect the user from a specific page.

    :param page: The page to start from, the user will be sent to next page in the list
    """
    session['currentUrl'] = page_list.next_path(page)
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/redirect_to_page/<path:page>")
def route_redirect_to_page(page):
    """
    ``/redirect_to_page/<path:page>``

    Redirect the user to a specific page path in ``PAGE_LIST``

    :param page:
    """
    session['currentUrl'] = page
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/end")
@verify_correct_page
@verify_session_valid
def route_end():
    """
    ``/end``

    Ends the experiment, marks the participants as finished, and shows the user's completion code if they have been
    given one. Can also be configured to redirect to an external URL.
    """
    p = db.Participant.query.get(session['participantID'])
    if p.timeEnded is None:
        p.timeEnded = datetime.datetime.utcnow()
    p.finished = True

    db.session.commit()

    if 'OUTGOING_URL' in current_app.config and current_app.config['OUTGOING_URL'] is not None:
        return redirect(current_app.config['OUTGOING_URL'])

    return render_template('end.html', code=session['code'] if 'code' in session else None)


@default.route("/user_active")
def route_user_active():
    if 'participantID' in session:
        participant = db.session.query(db.Participant).get(session['participantID'])
        participant.lastActiveOn = datetime.datetime.utcnow()
        db.session.commit()
    return ""


@default.route("/current_url")
def route_current_url():
    """
    ``/current_url``

    :return: The current URL of the user. For a new user, it returns "/".
    """
    if "currentUrl" in session:
        return session['currentUrl']
    else:
        return "/"


@default.route("/restart")
def route_restart():
    """
    ``/restart``

    Use this if you ever need to the user to start the experiment over for any reason.
    This tries to clear out all the cookies.
    """

    response = make_response(redirect("/"))
    sessionID = request.cookies.get("session", None)

    if sessionID:
        # Delete from DB
        ss = db.session.query(db.SessionStore).get(sessionID)

        if ss:
            db.session.delete(ss)
            db.session.commit()

    # Set cookie expiry for every route.
    for page in page_list.page_list:
        # TODO: Get all paths in page_list, for all conditions.
        if 'path' not in page:
            continue

        path = page['path']
        if not path.startswith("/"):
            path = "/" + path

        response.set_cookie('session', expires=0, path=path)

    return response


@default.route("/submit", methods=['POST'])
def submit():
    """
    ``/submit``

    Use this if you simply need to submit a form that redirects to the next page without doing anything with
    the form data.
    """
    return redirect("/redirect_next_page")


# Handy routes to save development time...


@default.route("/instructions/<pageName>", methods=['POST', 'GET'])
@verify_correct_page
@verify_session_valid
def route_instructions(pageName):
    """
    ``/instructions/<pageName>``

    Generic route to render instructions. The instructions are defined in HTML within a file and rendered in BOFS using
    the the templating system. A button to redirect to the next page in the study is shown after the instructions.

    Instruction HTML files can be placed in the project root directory's templates folder in
    ``/templates/instructions/...`` or in one of your blueprint's templates folder in
    ``/<my_blueprint>/templates/instructions/...``.

    The files must be in HTML format and use the ``.html`` extension. The ``pageName`` specified is the filename for the
    instructions, without the file extension.

    :param pageName: the name of the file to use to render the instructions (without the .html extension)
    """
    if request.method == "POST":
        return redirect(join_urls('/redirect_from_page', request.path))

    jinja = current_app.jinja_env
    instructionsTemplate = jinja.get_or_select_template("instructions/%s.html" % pageName)
    instructionsHtml = instructionsTemplate.render()

    return render_template("instructions.html", instructions=instructionsHtml)


@default.route("/simple/<pageName>", methods=['POST', 'GET'])
@verify_correct_page
@verify_session_valid
def route_simple_html(pageName):
    """
    ``/simple/<pageName>``

    Generic route to render simple Jinja 2 templates (or simple HTML pages) that do not need any additional Python code.
    The pages are defined in HTML/Jinja 2 within a file and rendered in BOFS using the templating system. Unlike the
    instruction pages, you are responsible for redirecting participants yourself (e.g., via a JavaScript redirect to
    ``/redirect_next_page``. A generic POST request to this route (such as from a form submission) will also trigger a
    redirection to the next page.

    Simple HTML files can be placed in the project root directory's templates folder in
    ``/templates/simple/...`` or in one of your blueprint's templates folder in
    ``/<my_blueprint>/templates/simple/...``.

    The files must be in HTML format and use the ``.html`` extension. The ``pageName`` specified is the filename for the
    html file, without the file extension.

    :param pageName: the name of the file to use to render the simple page (without the .html extension)
    """
    if request.method == "POST":
        return redirect(join_urls('/redirect_from_page', request.path))

    jinja = current_app.jinja_env
    simple_html = jinja.get_or_select_template("simple/%s.html" % pageName).render()

    return render_template("simple.html", simple_contents=simple_html)
