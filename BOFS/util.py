from datetime import datetime, timezone
from functools import wraps
from flask import request, redirect, session, current_app, g
import operator
from .globals import db
import math
from posixpath import join as urljoin
from typing import Union, Any


def utcnow_naive() -> datetime:
    """Naive UTC datetime — drop-in replacement for the deprecated ``datetime.utcnow()``.

    Returned value has no ``tzinfo`` so it stays compatible with SQLAlchemy
    ``DateTime`` columns (no ``timezone=True``) and with naive datetimes already
    persisted in existing databases.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def set_external_id_in_session(value):
    """Write the external ID to both ``session['externalID']`` (canonical)
    and ``session['mTurkID']`` (legacy alias).

    All BOFS-internal write sites go through this helper so the two keys
    never drift. User blueprints that write ``session['mTurkID']`` directly
    (as some longitudinal-study examples did before the rename) still work —
    :func:`get_external_id_from_session` falls back to the legacy key on read.
    """
    session['externalID'] = value
    session['mTurkID'] = value


def get_external_id_from_session():
    """Read the external ID, preferring the canonical ``session['externalID']``
    and falling back to the legacy ``session['mTurkID']``. Returns None if
    neither key is set.
    """
    return session.get('externalID') or session.get('mTurkID')


def update_participant_tracking(path):
    """Deprecated: use :meth:`BOFS.services.routing.ParticipantRoutingService.track_progress`.

    Kept as a thin wrapper for back-compat with researcher studies and
    third-party blueprints that import it.
    """
    from BOFS.services.routing import ParticipantRoutingService
    ParticipantRoutingService.from_app().track_progress(path)


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
        from BOFS.services.routing import ParticipantRoutingService

        currentUrl = request.url.replace(request.url_root, "")

        external_id = request.args.get('PROLIFIC_PID') or request.args.get('external_id')
        if external_id:
            set_external_id_in_session(external_id)

        # ``?source=`` is the explicit channel marker (e.g. "prolific",
        # "reddit", "email"). When PROLIFIC_PID is present without an
        # explicit source, infer ``prolific`` — the participant unambiguously
        # came from Prolific. We never override an already-set source.
        source = request.args.get('source')
        if not source and 'PROLIFIC_PID' in request.args:
            source = 'prolific'
        if source and not session.get('source'):
            session['source'] = source

        service = ParticipantRoutingService.from_app()

        wrong_page = service.enforce_current_page(currentUrl)
        if wrong_page is not None:
            return wrong_page

        bootstrapped = service.bootstrap_session_if_needed()
        if bootstrapped is not None and bootstrapped != currentUrl:
            return redirect(current_app.config["APPLICATION_ROOT"] + "/" + bootstrapped)

        ensure_response = service.ensure_participant_for_first_page()
        if ensure_response is not None:
            return ensure_response

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
            participant = db.session.get(db.Participant, session['participantID'])

            # See if the user exists in the database
            if participant is None:
                session.clear()
                return redirect('/')

            # Bind the participant session to the IP it was created from.
            # A stolen session cookie shouldn't work from another network.
            # Disabled for studies where participants legitimately switch
            # networks mid-session (mobile wifi <-> cellular).
            if (current_app.config.get('BRUTE_FORCE_PROTECTION', True)
                    and current_app.config.get('SESSION_BIND_TO_IP_PARTICIPANT', True)):
                from BOFS.services.brute_force import get_client_ip
                if participant.ipAddress and participant.ipAddress != get_client_ip():
                    session.clear()
                    return redirect('/')

        return f(*args, **kwargs)

    return decorated_function


def close_progress_submitted(path):
    """Deprecated: use :meth:`BOFS.services.routing.ParticipantRoutingService.close_progress`.

    Kept as a thin wrapper for back-compat with researcher studies and
    third-party blueprints that import it.
    """
    from BOFS.services.routing import ParticipantRoutingService
    ParticipantRoutingService.from_app().close_progress(path)


def page_tables(*table_names: str):
    """
    Decorator that declares which custom JSONTables a page-level view writes
    to, so the admin participant detail view can display rows from those
    tables when reviewing a participant's run.

    Apply to the view function whose route matches the path used in
    ``PAGE_LIST``. When one function handles both GET and POST (the common
    case) just decorate that. When a page renders from one URL but POSTs
    answers to a different URL, decorate the **GET** handler — the
    association is "this page is associated with these tables", not "this
    handler INSERTs into them".

    Example::

        @my_blueprint.route("/task", methods=['POST', 'GET'])
        @verify_correct_page
        @page_tables('answers')
        def task():
            ...

    Multiple names are allowed: ``@page_tables('answers', 'events')``.
    Stacking the decorator merges the lists.
    """
    def decorator(f):
        existing = list(getattr(f, '_bofs_tables', []))
        for name in table_names:
            if name not in existing:
                existing.append(name)
        f._bofs_tables = existing
        return f
    return decorator


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
    """Deprecated: use :meth:`BOFS.services.routing.ParticipantRoutingService.advance_to_next`.

    Closes the outgoing page's Progress row, advances ``session['currentUrl']``
    to the next page, and returns a redirect to it.
    """
    from BOFS.services.routing import ParticipantRoutingService
    return ParticipantRoutingService.from_app().advance_to_next(current_path)


def redirect_next_page():
    """Deprecated: use :meth:`BOFS.services.routing.ParticipantRoutingService.advance_to_next`.

    Like ``redirect_and_set_next_path`` but reads the current path from
    ``request.url_rule.rule``. Needs a valid app context to work.
    """
    from BOFS.services.routing import ParticipantRoutingService
    return ParticipantRoutingService.from_app().advance_to_next(request.url_rule.rule)


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

    current_path = request.path
    if current_path.startswith("/"):
        current_path = current_path[1:]

    # End pages (``/end`` and ``/end/<reason>``) never show the breadcrumb.
    # They're terminal: the participant has finished or been screened out,
    # and a "you were on Survey → Demographics → ..." trail at the moment
    # of exit is more noise than navigation. Returning empty here makes
    # the ``{% if crumbs %}`` guard in template.html collapse the block.
    if current_path == "end" or current_path.startswith("end/"):
        return []

    page_list = current_app.page_list.flat_page_list(hide_unresolved=True)
    crumbs = []

    # Create breadcrumbs. Match the active page by path rather than by
    # index, because ``hide_unresolved=True`` may have dropped earlier
    # entries that are still present in the unfiltered list ``get_index``
    # would consult.
    #
    # End entries (``path = "end"`` or ``path = "end/<reason>"``) never
    # show in the breadcrumb. They typically represent the terminus or a
    # screen-out exit; the participant is gone before the breadcrumb
    # would be re-rendered, and the per-reason entries exist mostly as
    # redirect/template configuration that the participant never "passes
    # through" in the page-flow sense.
    for page in page_list:
        name = page.get('name', '')
        if not name:
            continue
        path = page.get('path', '')
        if path == "end" or path.startswith("end/"):
            continue

        crumbs.append({
            'name': name,
            'active': path == current_path,
        })

    # Check for and handle any groupings of pages with the same name.
    for i, crumb in enumerate(crumbs):
        if i + 1 == len(crumbs):
            break

        crumbsInGroup = 1
        positionInGroup = 0

        if crumb['active']:
            positionInGroup = crumbsInGroup

        # Keep removing pages after the first one which have the same name.
        # The ``i + 1 < len(crumbs)`` bound is required because each pop
        # shrinks the list — without it, a run of duplicates that extends
        # to the final entry walks past the end of ``crumbs`` and raises.
        while i + 1 < len(crumbs) and crumbs[i]['name'] == crumbs[i + 1]['name']:
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


def provide_consent(assignCondition=True, logDisplaySize=True):
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
        from statistics import pstdev as p3std
        from statistics import pvariance as p3var
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