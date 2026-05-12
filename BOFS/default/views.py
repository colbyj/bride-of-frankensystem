from flask import Blueprint, render_template, current_app, request, make_response, abort
from urllib.parse import urlsplit
import traceback
from BOFS.JSONTable import JSONTable
from BOFS.util import *
from BOFS.globals import db, referrer, page_list, questionnaires, tables
from BOFS.BOFSSession import BOFSSessionInterface, BOFSSession
from BOFS.services.participant import ParticipantService
from BOFS.services.participant_questionnaire import ParticipantQuestionnaireService
from BOFS.services.session_recovery import SessionRecoveryService
from BOFS.services.condition_lookup import ConditionLookupMiss, ConditionLookupService


default = Blueprint('default', __name__)


def _render_condition_lookup_miss(external_id):
    return render_template(
        "condition_lookup_miss.html",
        external_id=external_id,
    ), 404


@default.route("/")
@verify_correct_page
def route_index():
    # @verify_correct_page redirects in normal flow; reaching this body means
    # the participant's session is in a corrupted state (e.g. empty
    # currentUrl). The 404 handler renders a recovery page with /restart link.
    abort(404)


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
    if all_conditions_disabled():
        return render_template("study_closed.html"), 503

    if request.method == 'POST':
        if 'email' in request.form and request.form['email'] != '':
            # We caught someone with our honeypot.
            return render_template("consent.html")

        try:
            provide_consent(True)
        except ConditionLookupMiss as miss:
            return _render_condition_lookup_miss(miss.external_id)
        if ParticipantService.use_debug_picker():
            return redirect("/debug_pick_condition")
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
    if all_conditions_disabled():
        return render_template("study_closed.html"), 503

    try:
        provide_consent(True, False)
    except ConditionLookupMiss as miss:
        return _render_condition_lookup_miss(miss.external_id)
    if ParticipantService.use_debug_picker():
        return redirect("/debug_pick_condition")
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
    if all_conditions_disabled():
        return render_template("study_closed.html"), 503

    if ParticipantService.use_debug_picker():
        return redirect("/debug_pick_condition")

    p = db.session.get(db.Participant, session['participantID'])
    try:
        ParticipantService.assign_condition_organic(p)
    except ConditionLookupMiss as miss:
        return _render_condition_lookup_miss(miss.external_id)

    return redirect("/redirect_from_page/assign_condition")


@default.route("/debug_pick_condition", methods=['POST', 'GET'])
def route_debug_pick_condition():
    """
    ``/debug_pick_condition``

    Debug-only intermediate page. When BOFS is run with ``-d``, the consent and
    ``/assign_condition`` routes redirect here instead of running the balancer
    automatically. Shows current per-condition counts (using the same filter the
    balancer uses), highlights the condition the balancer would have picked, and
    lets the developer override.
    """
    if not current_app.run_with_debugging:
        abort(404)

    if len(current_app.config['CONDITIONS']) == 0:
        abort(404)

    if all_conditions_disabled():
        return render_template("study_closed.html"), 503

    if 'participantID' not in session:
        return redirect("/")

    p = db.session.get(db.Participant, session['participantID'])
    if p is None:
        session.clear()
        return redirect("/")

    conditions = current_app.config['CONDITIONS']

    if request.method == 'POST':
        try:
            chosen = int(request.form['condition'])
        except (KeyError, ValueError, TypeError):
            abort(400)

        if chosen < 1 or chosen > len(conditions):
            abort(400)

        meta = conditions[chosen - 1]
        if 'enabled' in meta and meta['enabled'] is False:
            abort(400)

        ParticipantService.assign_condition_explicit(p, chosen)

        return redirect("/redirect_next_page")

    counts = db.Participant.balancer_counts()
    organic = db.Participant.compute_organic_condition()

    # If a CSV/DB lookup source is configured, run the lookup now (without
    # mutating the participant) and surface the result on the picker page so
    # it's evident whether the lookup found a hit. In production the picker
    # is bypassed and assign_condition would run the same lookup itself.
    lookup_configured = ConditionLookupService.is_configured()
    looked_up_condition = None
    if lookup_configured and p.mTurkID:
        looked_up_condition = ConditionLookupService.lookup(p.mTurkID)

    rows = []
    for idx, meta in enumerate(conditions):
        num = idx + 1
        rows.append({
            'num': num,
            'label': meta.get('label', 'Condition {}'.format(num)),
            'enabled': meta.get('enabled', True),
            'count': counts[idx] if idx < len(counts) else 0,
            'is_organic': (num == organic),
            'is_lookup': (num == looked_up_condition),
        })

    return render_template(
        "debug_pick_condition.html",
        rows=rows,
        organic=organic,
        lookup_configured=lookup_configured,
        looked_up_condition=looked_up_condition,
        external_id=p.mTurkID,
    )


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
        p = db.session.get(db.Participant, session['participantID'])
        p.mTurkID = str(request.form['mTurkID']).strip()

        session['mTurkID'] = p.mTurkID

        recovered_url = SessionRecoveryService.try_restore(p, p.mTurkID)
        if recovered_url:
            return redirect(recovered_url)

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
    service = ParticipantQuestionnaireService(session['participantID'])

    if request.method == 'POST':
        service.handle_submission(q, tag)

        return redirect(join_urls('/redirect_from_page', request.path))

    return service.render_questionnaire(q, 'questionnaire.html', tag)


@default.route("/questionnaire_question/<question_type>", methods=['POST'])
def route_questionnaire_question(question_type: str):
    """
    ``/questionnaire_question/<questionType>``

    Render a specific question type for the questionnaire. Only accepts POST requests.
    Data posted to this route must be a JSON object of the question data.
    """
    return ParticipantQuestionnaireService.render_questionnaire_question(question_type, request.json)


@default.route("/redirect_previous_page")
def route_redirect_previous_page():
    """
    ``/redirect_previous_page``

    Sends a user to the previous page. This is intended primarily for debugging purposes.
    """
    from BOFS.services.routing import ParticipantRoutingService
    return ParticipantRoutingService.from_app().go_back()


@default.route("/redirect_next_page")
def route_redirect_next_page():
    """
    ``/redirect_next_page``

    This is the preferred way of sending a user to the next page.
    """
    from BOFS.services.routing import ParticipantRoutingService
    return ParticipantRoutingService.from_app().advance_from_request()


@default.route("/redirect_from_page/<path:page>")
def route_redirect_from_page(page):
    """
    ``/redirect_from_page/<path:page>``

    Redirect the user from a specific page.

    :param page: The page to start from, the user will be sent to next page in the list
    """
    from BOFS.services.routing import ParticipantRoutingService
    return ParticipantRoutingService.from_app().advance_to_next(page)


@default.route("/redirect_to_page/<path:page>")
def route_redirect_to_page(page):
    """
    ``/redirect_to_page/<path:page>``

    Redirect the user to a specific page path in ``PAGE_LIST``

    :param page:
    """
    from BOFS.services.routing import ParticipantRoutingService
    return ParticipantRoutingService.from_app().go_to(page)


@default.route("/end")
@verify_correct_page
@verify_session_valid
def route_end():
    """
    ``/end``

    Ends the experiment, marks the participants as finished, and shows the user's completion code if they have been
    given one. Can also be configured to redirect to an external URL.
    """
    p = db.session.get(db.Participant, session['participantID'])
    if p.timeEnded is None:
        p.timeEnded = utcnow_naive()
    p.finished = True

    db.session.commit()

    if 'OUTGOING_URL' in current_app.config and current_app.config['OUTGOING_URL'] is not None:
        return redirect(current_app.config['OUTGOING_URL'])

    host = request.host.split(':')[0]
    is_local = host in ('127.0.0.1', 'localhost', '::1')
    if current_app.debug:
        restart_reason = "debug mode is enabled"
    elif is_local:
        restart_reason = "you are accessing the experiment locally"
    else:
        restart_reason = None

    return render_template('end.html',
                           code=session['code'] if 'code' in session else None,
                           restart_reason=restart_reason)


@default.route("/user_active")
def route_user_active():
    if 'participantID' in session:
        participant = db.session.get(db.Participant, session['participantID'])
        participant.lastActiveOn = utcnow_naive()
        db.session.commit()
    return ""


@default.route("/current_url")
def route_current_url():
    """
    ``/current_url``

    :return: The current URL of the user. For a new user, it returns "/".
    """
    body = session['currentUrl'] if "currentUrl" in session else "/"
    return body, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@default.route("/restart")
def route_restart():
    """
    ``/restart``

    Clears all participant/progress session state and redirects to the start
    of the experiment. Admin login state (``loggedIn``) is preserved so the
    admin does not need to re-authenticate after restarting a session.
    """
    was_logged_in = session.get('loggedIn', False)

    # save_session only assigns the FK columns when their keys exist in the
    # session dict; it never clears them. Null them out explicitly so the row
    # doesn't keep pointing at the previous participant. The cookie name is
    # the per-project ``bofs_<hash>`` produced by BOFSSessionInterface, not
    # the Flask default "session" — read it through the interface.
    sessionID = request.cookies.get(
        current_app.session_interface.get_cookie_name(current_app)
    )
    if sessionID:
        ss = db.session.get(db.SessionStore, sessionID)
        if ss:
            ss.participantID = None
            ss.mTurkID = None
            db.session.commit()

    session.clear()
    if was_logged_in:
        session['loggedIn'] = True

    return redirect("/")


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

    if 'participantID' in session:
        participant = db.session.get(db.Participant, session['participantID'])
    else:
        participant = None

    jinja = current_app.jinja_env
    instructionsTemplate = jinja.get_or_select_template("instructions/%s.html" % pageName)
    instructionsHtml = instructionsTemplate.render(participant=participant)

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

    if 'participantID' in session:
        participant = db.session.get(db.Participant, session['participantID'])
    else:
        participant = None

    jinja = current_app.jinja_env
    simple_html = jinja.get_or_select_template("simple/%s.html" % pageName).render(participant=participant)

    return render_template("simple.html", simple_contents=simple_html)


@default.route("/custom/<pageName>", methods=['POST', 'GET'])
@verify_correct_page
@verify_session_valid
def route_custom_html(pageName):
    """
    ``/custom/<pageName>``

    Generic route to render Jinja 2 templates as standalone pages with no BOFS template
    wrapping. Unlike simple pages, custom pages are not wrapped in the project's
    ``template.html``, so no header, breadcrumbs, or other BOFS chrome is rendered.
    The template is responsible for the entire HTML document.

    This is useful for tasks that need full control over the page (e.g., jsPsych or
    lab.js experiments that take over the viewport). As with simple pages, you are
    responsible for redirecting participants yourself (e.g., a JavaScript redirect to
    ``/redirect_next_page``). A POST to this route also redirects to the next page.

    Custom HTML files can be placed in the project root directory's templates folder in
    ``/templates/custom/...`` or in one of your blueprint's templates folder in
    ``/<my_blueprint>/templates/custom/...``.

    The files must be in HTML format and use the ``.html`` extension. The ``pageName``
    specified is the filename for the html file, without the file extension.

    :param pageName: the name of the file to use to render the custom page (without the .html extension)
    """
    if request.method == "POST":
        return redirect(join_urls('/redirect_from_page', request.path))

    if 'participantID' in session:
        participant = db.session.get(db.Participant, session['participantID'])
    else:
        participant = None

    return render_template("custom/%s.html" % pageName, participant=participant)
