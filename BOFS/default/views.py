from builtins import str
from builtins import range
import datetime
from flask import Blueprint, render_template, current_app, request, _app_ctx_stack
from BOFS.util import *
from BOFS.globals import db, referrer, page_list, questionnaires
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
        provide_consent(True)
        return redirect("/redirect_next_page")
    return render_template("consent.html")


# Sets participant's condition to -1 always
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

        # Check to see if this MTurkID has been used already. If so, grab their previously assigned condition
        pOthers = db.session.query(db.Participant). \
            filter(
            db.Participant.mTurkID == p.mTurkID,
            db.Participant.participantID != p.participantID,
            db.Participant.condition != -1
        ).all()

        if pOthers and len(pOthers) > 0:
            p.condition = pOthers[0].condition
            for pOther in pOthers:
                # Reset the condition for the past attempt in order to
                # not screw up condition assignment for everyone else.
                pOther.condition = -1
            session['condition'] = p.condition

        session['code'] = p.code
        session['mTurkID'] = p.mTurkID

        db.session.commit()
        return redirect("/redirect_next_page")

    return render_template('mturk_id.html', crumbs=create_breadcrumbs())


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
                           crumbs=create_breadcrumbs(),
                           q=q.jsonData,
                           timeStarted=datetime.datetime.now())


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
    p.timeEnded = datetime.datetime.now()
    p.finished = True

    db.session.commit()

    return render_template('end.html', code=session['code'] if 'code' in session else None)


@default.route("/user_active")
def route_user_active():
    if 'participantID' in session:
        participant = db.session.query(db.Participant).get(session['participantID'])
        participant.lastActiveOn = datetime.datetime.now()
        db.session.commit()
    return ""


@default.route("/current_url")
def route_current_url():
    if "currentUrl" in session:
        return session['currentUrl']
    else:
        return "/"


@default.route("/restart")
def route_restart():
    """
    Use this if you ever need to the user to start the experiment over for any reason.
    I can't guantee this will always work; the safest method is always to clear the browser's cookies.
    :return:
    """
    if session.get("loggedIn", False):
        # If I clear the session, I don't see to be able to use if immediately after.
        # Therefore, I'm using the suggested alternative from SO:
        #  https://stackoverflow.com/questions/27747578/how-do-i-clear-a-flask-session/51395792
        [session.pop(key) for key in list(session.keys()) if
         key != '_flashes' and key != 'loggedIn' and key != '_permanent']
    else:
        session.clear()
    return redirect("/")


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

