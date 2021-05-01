from builtins import str
from builtins import range
import datetime
from flask import Blueprint, render_template, current_app, request, make_response, _app_ctx_stack
from BOFS.util import *
from BOFS.globals import db, referrer, page_list, questionnaires
from BOFS.BOFSFlask import BOFSSessionInterface, BOFSSession
import os.path
import uuid


default = Blueprint('default', __name__)


@default.route("/")
@verify_correct_page
def route_index():
    return "You shouldn't be able to see this."


@default.route("/consent", methods=['POST', 'GET'])
@verify_correct_page
def route_consent():
    """
    This shows a consent form. Upon submission, the participant entry is created in the database, they
    are assigned a condition, and the session variables are set.
    This is typically the first page you will use in PAGE_LIST. If not, use one of
    * `/consent_nc`
    * `/create_participant`
    * `/create_participant_nc`
    :return:
    """
    if request.method == 'POST':
        if 'email' in request.form and request.form['email'] != '':
            # We caught someone with our honeypot.
            return render_template("consent.html")

        provide_consent(True)
        return redirect("/redirect_next_page")

    return render_template("consent.html")


# Sets a participant's condition to 0 instead of assigning it as normal
@default.route("/consent_nc", methods=['POST', 'GET'])
@verify_correct_page
def route_consent_nc():
    """
    This acts just like `/consent`, except it does not assign the user a condition (defaults to 0).
    :return:
    """
    if request.method == 'POST':
        provide_consent(False)
        return redirect("/redirect_next_page")
    return render_template("consent.html")


# Use this route in place of /consent, if you want to bypass the consent form.
@default.route("/create_participant")
def route_create_participant():
    """
    This creates the participant in the database and sets up the session variables. Use if you don't need to
    show a consent form.
    :return:
    """
    provide_consent(True)
    return redirect("/redirect_next_page")


# Use this route in place of /consent_nc, if you want to bypass the consent form without assigning a condition.
@default.route("/create_participant_nc")
def route_create_participant_nc():
    """
    This creates the participant in the database and sets up the session variables. Use if you don't need to
    show a consent form.
    This does not assign the participant a condition (defaults to 0)
    and so could be used in conjuction with `/assign_condition`.
    :return:
    """
    provide_consent(False)
    return redirect("/redirect_next_page")


@default.route("/assign_condition")
@verify_session_valid
@verify_correct_page
def route_assign_condition():
    """
    Typically conditions are assigned upon consent. Use this page if you want to assign a condition later on in
    the experiment. This might be used, for example, after several initial questionnaires, so that participants
    who fail to actually attempt the task don't end up getting assigned a condition.
    :return:
    """
    p = db.session.query(db.Participant).get(session['participantID'])
    p.assign_condition()
    db.session.commit()

    session['condition'] = p.condition

    return redirect("/redirect_next_page")


@default.route("/startMTurk", methods=['POST', 'GET'])  # Deprecated
@default.route("/start_mturk", methods=['POST', 'GET'])
@verify_correct_page
def route_start_mturk():
    """
    If we are using a platform where the user has a unique (and anonymous) ID associated with their account,
    then you can use this page to request that ID. This is set up to work with Mechanical Turk, but the
    template can be overwritten to request different types of ID.
    :return:
    """
    if request.method == 'POST':
        p = db.Participant.query.get(session['participantID'])
        p.mTurkID = str(request.form['mTurkID']).strip()
        p.code = uuid.uuid4().hex

        session['code'] = p.code
        session['mTurkID'] = p.mTurkID

        # Don't try to load any past attempts if this config option is set
        if not current_app.config['RETRIEVE_SESSIONS']:
            return redirect('/redirect_next_page')

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
                pFromMTurkID = pFromMTurkID.filter(db.Participant.finished != True)

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
                if 'currentUrl' in dictData and session['currentUrl'] not in ('startMTurk', 'start_mturk', 'consent'):
                    return redirect(session['currentUrl'])

        return redirect('/redirect_next_page')

    return render_template('mturk_id.html')


@default.route("/questionnaire/<questionnaireName>", methods=['POST', 'GET'])
@default.route("/questionnaire/<questionnaireName>/<tag>", methods=['POST', 'GET'])
@verify_correct_page
def route_questionnaire(questionnaireName, tag=""):
    """
    Render a questionnaire.
    :param questionnaireName: The name of the json file (without the .json extension).
    :param tag: If the same questionnaire is to be displayed more than once, provide it with a
                unique tag (e.g., "before" or "after" or "1")
    :return:
    """
    q = questionnaires[questionnaireName]

    if request.method == 'POST':
        q.handle_questionnaire(tag)

        return redirect("/redirect_next_page")

    return render_template('questionnaire.html',
                           tag=tag,
                           q=q.jsonData,
                           timeStarted=datetime.datetime.utcnow())


@default.route("/redirect_previous_page")
def route_redirect_previous_page():
    """
    Sends a user to the previous page. This is intended primarily for debugging purposes.
    :return:
    """
    session['currentUrl'] = page_list.previous_path(session['currentUrl'])
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/redirect_next_page")
def route_redirect_next_page():
    """
    This is the preferred way of sending a user to the next page.
    :return:
    """
    if not request is None and not request.referrer is None:
        currentPage = str.replace(str(request.referrer), request.host_url, "")
    else:
        currentPage = session['currentUrl']

    if currentPage == "end":
        return redirect(current_app.config["APPLICATION_ROOT"] + "/end")

    session['currentUrl'] = page_list.next_path(currentPage)
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/redirect_from_page/<path:page>")
def route_redirect_from_page(page):
    """
    Redirect the user from a specific page.
    :param page: The page to start from, the user will be sent to next page in the list
    :return:
    """
    session['currentUrl'] = page_list.next_path(page)
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/redirect_to_page/<path:page>")
def route_redirect_to_page(page):
    """
    Redirect the user to a specific page path in PAGE_LIST
    :param page:
    :return:
    """
    session['currentUrl'] = page
    nextUrl = current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl']

    return redirect(nextUrl)


@default.route("/end")
@verify_correct_page
@verify_session_valid
def route_end():
    """
    Ends the experiment and shows the user's completion code, if they have been given one.
    :return:
    """
    p = db.Participant.query.get(session['participantID'])
    p.timeEnded = datetime.datetime.utcnow()
    p.finished = True

    db.session.commit()

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
    if "currentUrl" in session:
        return session['currentUrl']
    else:
        return "/"


#import requests.cookies

@default.route("/restart")
def route_restart():
    """
    Use this if you ever need to the user to start the experiment over for any reason.
    This tries to clear out all of the cookies.
    :return:
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
    Use this if you simply need to submit a form that redirects to the next page without doing anything with
    the form data.
    :return:
    """
    return redirect("/redirect_next_page")


# Handy routes to save development time...


@default.route("/instructions/<pageName>", methods=['POST', 'GET'])
@verify_correct_page
@verify_session_valid
def route_instructions(pageName):
    """
    Generic page to render instructions. Instructions can be inside of blueprints.
    Find html at "instructions/<pageName>.html" and insert it as a variable into instructions.html
    :param pageName:
    :return:
    """
    if request.method == "POST":
        return redirect("/redirect_next_page")

    jinja = current_app.jinja_env
    instructionsTemplate = jinja.get_or_select_template("instructions/%s.html" % pageName)
    instructionsHtml = instructionsTemplate.render()

    return render_template("instructions.html", instructions=instructionsHtml)

