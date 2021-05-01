from __future__ import print_function
from __future__ import absolute_import
from builtins import str
from functools import wraps
from flask import request, redirect, session, current_app
import operator
from .globals import db
import math
import datetime


# Decorator to help views verify whether the user is on the right page
def verify_correct_page(f):
    """
    A decorator to be used on routes/views, which checks the the user is on the correct page. Checks
    ``session['currentUrl']``. If the user is on the wrong page, they will be redirected to the correct page.

    .. note::
        * Should be used just on routes after the user's session is created (usually after the consent form).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        currentUrl = request.url.replace(request.url_root, "")

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

        # Add or update their progress
        if 'participantID' in session:
            participant = db.session.query(db.Participant).get(session['participantID'])
            participant.lastActiveOn = datetime.datetime.utcnow()
            db.session.commit()

            progress = db.session.query(db.Progress).filter(
                db.Progress.participantID == session['participantID'],
                db.Progress.path == currentUrl
            ).one_or_none()

            if progress is None:
                progress = db.Progress()
                progress.participantID = session['participantID']
                progress.path = currentUrl
                progress.startedOn = datetime.datetime.utcnow()
                db.session.add(progress)
                db.session.commit()

            if request.method == "POST":
                progress.submittedOn = datetime.datetime.utcnow()
                db.session.commit()

        return f(*args, **kwargs)
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
            #if participant.ipAddress != request.environ['REMOTE_ADDR']:
            #    session.clear()
            #    return redirect('/')

        return f(*args, **kwargs)
    return decorated_function


def redirect_and_set_next_path(current_path=None):
    """
    Uses the next_path_in_list() method to redirect the user
    
    :param str current_path: The user's current path
    :returns: str -- the next path in PAGE_LIST which the user should be sent to.
    """
    session['currentUrl'] = current_app.page_list.next_path(current_path)
    return redirect(current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl'])


def redirect_next_page(request):
    """
    Like redirect_and_set_next_path but takes in the Flask request variable instead.
    :param request:
    :return:
    """
    session['currentUrl'] = current_app.page_list.next_path(request.url_rule.rule)
    return redirect(current_app.config["APPLICATION_ROOT"] + "/" + session['currentUrl'])


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
        if i+1 == len(crumbs):
            break

        crumbsInGroup = 1
        positionInGroup = 0

        if crumb['active']:
            positionInGroup = crumbsInGroup

        # Keep removing pages after the first one which have the same name.
        while crumbs[i]['name'] == crumbs[i+1]['name']:
            removedCrumb = crumbs.pop(i+1)

            crumbsInGroup += 1

            if removedCrumb['active']:
                crumbs[i]['active'] = True
                positionInGroup = crumbsInGroup

        if crumbsInGroup > 1 and positionInGroup > 0:
            crumbs[i]['name'] += str.format(u" ({0} of {1})", positionInGroup, crumbsInGroup)
        elif crumbsInGroup > 1:
            crumbs[i]['name'] += str.format(u" ({0})", crumbsInGroup)

    return crumbs


def fetch_attr(obj, attribute, *args):
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


def fetch_current_condition():
    try:
        # If session exists, and condition is a key, then let's grab the current condition!
        if not session is None and 'condition' in session:
            condition = session['condition']
            if condition == -1:
                condition = 0
            return condition
        return 0
    except:
        return None  # This is almost definitely a "Working outside of request context" error


def fetch_condition_count():
    if not "CONDITIONS_NUM" in current_app.config:
        return 1

    conditions = current_app.config["CONDITIONS_NUM"]

    if conditions <= 0:
        return 1

    return conditions


# This is useful only after data has been collected.
def fetch_condition_count_db():
    return db.session.query(db.func.max(db.Participant.condition)).one()[0]


# This needs to be used inside of a route, otherwise session, request won't work.
def provide_consent(assignCondition=True, logDisplaySize=True):
    from flask import request, session
    from BOFS.globals import db
    import datetime

    p = db.Participant()
    p.ipAddress = request.environ['REMOTE_ADDR']  # request.headers.get('X-Real-IP')  # request.remote_addr
    p.userAgent = request.user_agent.string
    p.timeStarted = datetime.datetime.utcnow()

    if assignCondition:
        p.assign_condition()
    else:
        p.condition = 0

    db.session.add(p)
    db.session.commit()

    session['participantID'] = p.participantID
    session['condition'] = p.condition

    if logDisplaySize:
        entry = db.Display()
        entry.participantID = session['participantID']
        entry.dppx = request.form['dppx']
        entry.screenWidth = request.form['screenWidth']
        entry.screenHeight = request.form['screenHeight']
        entry.innerWidth = request.form['innerWidth']
        entry.innerHeight = request.form['innerHeight']

        db.session.add(entry)
        db.session.commit()


# Provides some error checking for when converting results of form submission
def float_or_0(value):
    value = float(value)

    if math.isnan(value):
        return 0.0
    return value


def int_or_0(value):
    value = int(value)

    if math.isnan(value):
        return 0
    return value


def display_time(seconds):
    if not seconds:
        return seconds
    if seconds > 60:
        return str("{:.0f}:{:02.0f}").format((seconds / 60), (seconds % 60))
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