from functools import wraps
from flask import request, redirect, session, current_app, g
import operator
from .globals import db
import math
import datetime
import uuid
from posixpath import join as urljoin
from typing import Union, Any


def update_participant_tracking(path):
    """
    Refresh ``Participant.lastActiveOn``, ensure a ``Progress`` row exists for
    *(participant, path)*, and (on POST) close ``submittedOn``.

    Called from ``BOFSFlask.before_request_`` for every participant-flow
    request — decorated or not — so custom blueprint routes that forget
    ``@verify_correct_page`` still get tracked.

    No-ops when there's no participant in session or the participant row is
    missing (e.g. cleared mid-flow).
    """
    if 'participantID' not in session:
        return

    participant = db.session.query(db.Participant).get(session['participantID'])
    if participant is None:
        return

    participant.lastActiveOn = datetime.datetime.utcnow()
    db.session.commit()

    progress = db.session.query(db.Progress).filter(
        db.Progress.participantID == session['participantID'],
        db.Progress.path == path,
    ).one_or_none()

    if progress is None:
        progress = db.Progress()
        progress.participantID = session['participantID']
        progress.path = path
        progress.startedOn = datetime.datetime.utcnow()
        db.session.add(progress)
        db.session.commit()

    if request.method == "POST":
        progress.submittedOn = datetime.datetime.utcnow()
        db.session.commit()


# Decorator to help views verify whether the user is on the right page
def verify_correct_page(f):
    """
    A decorator to be used on routes/views, which checks the the user is on the correct page. Checks
    ``session['currentUrl']``. If the user is on the wrong page, they will be redirected to the correct page.

    Participant progress tracking (``lastActiveOn``, ``Progress`` rows) is
    handled by ``BOFSFlask.before_request_`` for every participant-flow
    request, so this decorator is no longer responsible for that. It is still
    the right place to enforce page-list ordering and bootstrap session state.

    .. note::
        * Should be used just on routes after the user's session is created (usually after the consent form).
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        currentUrl = request.url.replace(request.url_root, "")

        if 'PROLIFIC_PID' in request.args:
            session['mTurkID'] = request.args['PROLIFIC_PID']

        if 'external_id' in request.args:
            session['mTurkID'] = request.args['external_id']

        # Don't allow users to skip things or go back. Redirect to the correct page if they try.
        if 'currentUrl' in session and currentUrl != session['currentUrl']:
            return redirect(str.format(u"{}/{}", current_app.config["APPLICATION_ROOT"], str(session['currentUrl'])))

        # If user hasn't been here before, set their current URL to the first one in the list.
        if not 'currentUrl' in session:
            session['currentUrl'] = current_app.page_list.flat_page_list()[0]['path']

            # If the user happens to be on the page they are already supposed to be at, continue as normal
            # This should only happen for the first page in the experiment.
            if session['currentUrl'] == currentUrl:
                return f(*args, **kwargs)

            return redirect(current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl'])

        return f(*args, **kwargs)

    decorated_function._bofs_verify_correct_page = True
    return decorated_function


def verify_session_valid(f):
    """
    A decorator to be used on routes/views, which checks for the existence of the 'currentUrl' key in ``session``.

    .. note::
        * Should be used just on routes after the session is created (for example, after the initial questionnaire).
        * The ``/submit`` path is where the value of ``session['currentUrl']`` is set.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # The user shouldn't be here yet, redirect to the start
        if not 'currentUrl' in session:
            return redirect('/')

        if 'participantID' in session:
            participant = db.Participant.query.get(session['participantID'])

            # See if the user exists in the database
            if participant is None:
                session.clear()
                return redirect('/')
            # See that the user's IP address matches what's in the database
            # if participant.ipAddress != request.environ['REMOTE_ADDR']:
            #    session.clear()
            #    return redirect('/')

        return f(*args, **kwargs)

    return decorated_function


def close_progress_submitted(path):
    """
    Close out the participant's Progress row for *path* by setting
    ``submittedOn`` to now, if it is still NULL.

    No-op when there's no participant in session, no path, or no matching
    Progress row. Safe to call from any forward-navigation chokepoint.
    """
    if not path:
        return
    if 'participantID' not in session:
        return

    progress = db.session.query(db.Progress).filter(
        db.Progress.participantID == session['participantID'],
        db.Progress.path == path,
    ).one_or_none()

    if progress is None or progress.submittedOn is not None:
        return

    progress.submittedOn = datetime.datetime.utcnow()
    db.session.commit()


def suppress_activity_polling(f):
    """
    Decorator that opts a route out of the auto-injected activity-polling
    script (see ``BOFSFlask.after_request_``). Use this on custom pages that
    run their own JS and don't want a framework script appended to the body.

    Applying this decorator also suppresses the startup warning about a
    missing ``@verify_correct_page``, since reaching for this opt-out
    implies the route is being managed manually by the researcher.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.bofs_skip_activity_polling = True
        return f(*args, **kwargs)
    decorated_function._bofs_suppress_activity_polling = True
    return decorated_function


def redirect_and_set_next_path(current_path=None):
    """
    Uses the next_path_in_list() method to redirect the user. Also closes the
    outgoing page's Progress row (sets ``submittedOn``) so custom pages that
    navigate via GET don't leave Progress rows perpetually open.

    :param str current_path: The user's current path
    :returns: str -- the next path in PAGE_LIST which the user should be sent to.
    """
    close_progress_submitted(current_path)
    session['currentUrl'] = current_app.page_list.next_path(current_path)
    return redirect(current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl'])


def redirect_next_page():
    """
    Like redirect_and_set_next_path but uses the Flask request variable instead.
    Needs a valid app context to work.
    Redirects user to the next page based on their present URL (from the request).
    """
    return redirect_and_set_next_path(request.url_rule.rule)


def join_urls(path: str, *paths: str):
    paths = list(paths)
    for i in range(len(paths)):
        if paths[i] != None and paths[i] != '' and paths[i][0] == '/':
            paths[i] = paths[i][1:]
    return urljoin(path, *tuple(paths))


def create_breadcrumbs():
    """
    An optional function, the result of which can be passed to templates which extend the base ``template.html`` file.
    Pages with the same name will be represented as Page Name (3) or **Page Name (2 of 3)** when the user is on that
    particular page.

    :returns: A list of "breadcrumbs", each of which are a dictionary with a human-readable name for the path, and
     whether or not that page is the active page, meaning it should be made bold.
    """

    page_list = current_app.page_list.flat_page_list()
    currentIndex = current_app.page_list.get_index(request.path)
    crumbs = []

    # Create breadcrumbs (duplicates handled no differently than anything else)
    for i, page in enumerate(page_list):
        if page['name'] == '':
            continue

        crumb = {'name': page['name'], 'active': False}

        if page_list.index(page) == currentIndex:
            crumb['active'] = True

        crumbs.append(crumb)

    # Check for and handle any groupings of pages with the same name.
    for i, crumb in enumerate(crumbs):
        if i + 1 == len(crumbs):
            break

        crumbsInGroup = 1
        positionInGroup = 0

        if crumb['active']:
            positionInGroup = crumbsInGroup

        # Keep removing pages after the first one which have the same name.
        while crumbs[i]['name'] == crumbs[i + 1]['name']:
            removedCrumb = crumbs.pop(i + 1)

            crumbsInGroup += 1

            if removedCrumb['active']:
                crumbs[i]['active'] = True
                positionInGroup = crumbsInGroup

        if crumbsInGroup > 1 and positionInGroup > 0:
            crumbs[i]['name'] += str.format(u" ({0} of {1})", positionInGroup, crumbsInGroup)
        elif crumbsInGroup > 1:
            crumbs[i]['name'] += str.format(u" ({0})", crumbsInGroup)

    return crumbs


def fetch_attr(obj, attribute, *args) -> Any:
    """
    Returns attribute value, or calls a method. Can handle attributes nested with dots (.)

    This is similar to Python's built in [https://docs.python.org/2/library/functions.html#getattr getattr()],
    but with support for an arbitrary depth.
    """
    try:
        getAttr = operator.attrgetter(attribute)
        attr = getAttr(obj)
    except AttributeError as e:
        return None

    if callable(attr):
        return attr()
    else:
        return attr


def fetch_current_condition() -> Union[int, None]:
    """
    :return: The participant's current condition, as an integer (or None)
    """
    from BOFS.services.participant import ParticipantService
    return ParticipantService.current_condition()


def fetch_condition_count() -> int:
    from BOFS.services.participant import ParticipantService
    return ParticipantService.condition_count()


def all_conditions_disabled() -> bool:
    """
    True iff CONDITIONS is non-empty AND every condition has enabled=False.
    Used to halt new participant intake when a researcher has disabled every
    condition from the admin panel mid-study.
    """
    from BOFS.services.participant import ParticipantService
    return ParticipantService.all_conditions_disabled()


def fetch_condition_count_db():
    """
    This is useful only after data has been collected.
    :return:
    """
    from BOFS.services.participant import ParticipantService
    return ParticipantService.max_assigned_condition_db()


def provide_consent(assignCondition=True, logDisplaySize=False):
    """
    This needs to be used inside a route, otherwise session and request won't work.

    :param assignCondition:
    :param logDisplaySize:
    :return: A Participant object
    """
    from BOFS.services.participant import ParticipantService
    return ParticipantService.provide_consent(
        assign_condition=assignCondition,
        log_display_size=logDisplaySize,
    )


# Provides some error checking for when converting results of form submission
def float_or_0(value) -> float:
    """
    Cast the value to a float if it can, otherwise return 0.0.

    :param value: value to be cast
    :return: the value as a float (or 0.0)
    """
    try:
        value = float(value)
    except (ValueError, TypeError):
        return 0.0

    if math.isnan(value):
        return 0.0
    return value


def int_or_0(value) -> int:
    """
    Cast the value to an int if it can, otherwise return 0.

    :param value: value to be cast
    :return: the value as a int (or 0)
    """
    try:
        value = int(value)
    except (ValueError, TypeError):
        return 0

    if math.isnan(value):
        return 0
    return value


def display_time(seconds):
    if not seconds:
        return seconds
    if seconds > 60:
        return str("{}:{:02d}").format(int(seconds / 60), int(seconds % 60))
    else:
        return str(int(seconds))


numpy = False
py3statistics = False

try:
    from numpy import mean as npmean
    from numpy import std as npstd
    from numpy import var as npvar
    from numpy import median as npmedian

    numpy = True
except Exception as e1:
    try:
        from statistics import mean as p3mean
        from statistics import stdev as p3std
        from statistics import variance as p3var
        from statistics import median as p3median

        py3statistics = True
    except Exception as e2:
        print("Warning: Unable to import either NumPy or Python 3's statistics library!")


# Some math functions
def mean(numbers):
    if numpy:
        return npmean(numbers)
    elif py3statistics:
        return p3mean(numbers)
    return float(sum(numbers)) / max(len(numbers), 1)


def variance(numbers):
    if numpy:
        return npvar(numbers)
    elif py3statistics:
        return p3var(numbers)
    mn = mean(numbers)
    variance = sum([(e - mn) ** 2 for e in numbers]) / float(len(numbers))
    return variance


def std(numbers):
    if numpy:
        return npstd(numbers)
    elif py3statistics:
        return p3std(numbers)
    return math.sqrt(variance(numbers))


def median(numbers):
    if numpy:
        return npmedian(numbers)
    elif py3statistics:
        return p3median(numbers)
    quotient, remainder = divmod(len(numbers), 2)
    if remainder:
        return sorted(numbers)[quotient]
    return sum(sorted(numbers)[quotient - 1:quotient + 1]) / 2.


stdev = std
var = variance