from urllib.parse import urlsplit

from flask import current_app, redirect, render_template, request, session

from BOFS.globals import db
from BOFS.util import utcnow_naive


class ParticipantRoutingService:
    """Owns participant navigation: page resolution, ``session['currentUrl']``
    writes, progress tracking, and redirect-URL construction.

    Layered atop ``PageList`` (which remains a pure config/sequence object).
    Instances are cheap and request-scoped; build one per call via
    :meth:`from_app`.
    """

    def __init__(self, session, page_list, application_root=""):
        self.session = session
        self.page_list = page_list
        self.application_root = application_root or ""

    @classmethod
    def from_app(cls):
        """Construct from the active Flask request context.

        Reads :data:`flask.session`, ``current_app.page_list``, and
        ``current_app.config['APPLICATION_ROOT']``.
        """
        return cls(
            session=session,
            page_list=current_app.page_list,
            application_root=current_app.config.get("APPLICATION_ROOT", "") or "",
        )

    # ----- Read-only accessors -----------------------------------------

    def current_url(self):
        return self.session.get("currentUrl")

    def current_index(self, path=None):
        if path is None:
            path = request.path
        return self.page_list.get_index(path)

    def next_path(self, from_path=None):
        return self.page_list.next_path(from_path)

    def previous_path(self, from_path=None):
        return self.page_list.previous_path(from_path)

    # ----- Navigation --------------------------------------------------

    def advance_to_next(self, from_path=None):
        """Close progress on ``from_path``, advance ``session['currentUrl']``
        to the next page in the flat list, and return a redirect to it.
        """
        self.close_progress(from_path)
        self.session["currentUrl"] = self.page_list.next_path(from_path)
        return redirect(self.application_root + "/" + self.session["currentUrl"])

    def advance_from_request(self):
        """Resolve the participant's "from" page from request context, then
        advance.

        Resolution precedence (matches the legacy ``/redirect_next_page``
        handler):

        1. ``request.url_rule.rule`` — set when a researcher's view function
           calls into this service directly.
        2. ``request.referrer`` path — set when the browser hit
           ``/redirect_next_page`` itself.
        3. ``session['currentUrl']`` — ultimate fallback.

        Includes the self-loop guard for ``/redirect_next_page`` and the
        ``end`` short-circuit (close progress, redirect to ``/end``).
        """
        current_page = None
        if request is not None:
            if request.url_rule is not None:
                current_page = request.url_rule.rule
            elif request.referrer is not None:
                parsed = urlsplit(request.referrer)
                if len(parsed.path) > 0:
                    current_page = parsed.path

        if not current_page or not isinstance(current_page, str):
            current_page = self.session.get("currentUrl")

        if current_page and current_page.strip("/") == "redirect_next_page":
            current_page = self.session.get("currentUrl")

        # Stale request after /restart cleared the session — bounce home and
        # let verify_correct_page rebuild the flow.
        if not current_page:
            return redirect(self.application_root + "/")

        if current_page == "end":
            self.close_progress(current_page)
            return redirect(self.application_root + "/end")

        return self.advance_to_next(current_page)

    def go_to(self, path):
        """Set ``session['currentUrl']`` to *path* and redirect there."""
        self.session["currentUrl"] = path
        return redirect(self.application_root + "/" + self.session["currentUrl"])

    def go_back(self):
        """Move ``session['currentUrl']`` one step back in the flat list."""
        self.session["currentUrl"] = self.page_list.previous_path(
            self.session.get("currentUrl")
        )
        return redirect(self.application_root + "/" + self.session["currentUrl"])

    # ----- @verify_correct_page helpers --------------------------------

    def bootstrap_session_if_needed(self):
        """If ``session['currentUrl']`` is missing, set it to the first page
        in the flat list and return that path. Returns ``None`` when the
        session already has a current URL.
        """
        if "currentUrl" in self.session:
            return None
        first_path = self.page_list.flat_page_list()[0]["path"]
        self.session["currentUrl"] = first_path
        return first_path

    def enforce_current_page(self, current_url):
        """Return a redirect when the participant's session expects a
        different page than *current_url*. Returns ``None`` when there is no
        expected page (caller should bootstrap) or when it matches.
        """
        expected = self.session.get("currentUrl")
        if expected is None:
            return None
        if current_url == expected:
            return None
        return redirect(self.application_root + "/" + str(expected))

    def ensure_participant_for_first_page(self):
        """Transparently create a Participant when the first ``PAGE_LIST``
        entry is not one of the routes that bootstrap a participant on their
        own (``consent``, ``consent_nc``, ``create_participant``,
        ``create_participant_nc``) and is not ``end`` (a deliberate
        terminus). Runs the same code path as ``/create_participant``, so a
        researcher whose ``PAGE_LIST`` starts with ``questionnaire/foo``
        sees a fully-set-up participant on first request.

        Returns a Flask response when the caller should short-circuit:

        * rendered ``study_closed.html`` (503) if all conditions are disabled
        * rendered ``condition_lookup_miss.html`` (404) if an external-ID
          lookup is configured and the participant's ID isn't found
        * redirect to ``/debug_pick_condition`` in debug mode with conditions
          configured

        Returns ``None`` when no action is needed (the common case — a
        creation route is at the front, or a participant already exists) or
        when creation completed silently and the wrapped view should run.
        """
        from BOFS.services.participant import (
            CREATION_ROUTES,
            ParticipantService,
        )
        from BOFS.services.condition_lookup import ConditionLookupMiss

        if "participantID" in self.session:
            return None

        flat = self.page_list.flat_page_list()
        if not flat:
            return None
        first_path = flat[0]["path"]

        # An ``end`` or ``end/<reason>`` entry as the first PAGE_LIST step is
        # a deliberate "study closed" / "screened out" terminus — let
        # route_end render without a participant rather than auto-creating
        # one just to immediately mark it finished.
        if first_path in CREATION_ROUTES or first_path == "end" or first_path.startswith("end/"):
            return None

        if ParticipantService.all_conditions_disabled():
            ParticipantService.provide_quota_full()
            return redirect(self.application_root + "/end/quota_full")

        try:
            p = ParticipantService.provide_consent(assign_condition=True)
        except ConditionLookupMiss as miss:
            return render_template(
                "condition_lookup_miss.html",
                external_id=miss.external_id,
            ), 404

        if p.isCrawler:
            return redirect(self.application_root + "/end/bot")

        if ParticipantService.use_debug_picker():
            return redirect(self.application_root + "/debug_pick_condition")

        return None

    def require_participant(self, current_url):
        """Return a redirect to the study start when *current_url* is a page
        that needs a participant in session but none exists.

        :meth:`ensure_participant_for_first_page` only lazy-creates a
        participant when the *first* PAGE_LIST entry is a content route. A
        participant who reaches a deeper content page
        (questionnaire/instructions/simple/custom) with a session that still
        has ``currentUrl`` but has lost ``participantID`` (a corrupted or
        partially-cleared session) would otherwise fall through to the view,
        which dereferences ``session['participantID']`` and 500s. Clear the
        broken session and send them back to the start so it re-bootstraps
        onto the first page — the same recovery ``verify_session_valid`` and
        ``route_debug_pick_condition`` already use for a missing/invalid
        participant.

        Returns ``None`` when a participant exists or when *current_url* is a
        route that legitimately runs without one (the consent/creation
        variants, the index, and the ``end`` terminus).
        """
        if "participantID" in self.session:
            return None

        from BOFS.services.participant import CREATION_ROUTES

        path = urlsplit(current_url or "").path.strip("/")
        if (path == "" or path in CREATION_ROUTES
                or path == "end" or path.startswith("end/")):
            return None

        # Stale currentUrl would bounce an index redirect straight back here
        # (enforce_current_page), so clear it for a clean re-bootstrap.
        self.session.clear()
        return redirect(self.application_root + "/")

    # ----- Progress tracking -------------------------------------------

    def track_progress(self, path):
        """Refresh ``Participant.lastActiveOn``, ensure a ``Progress`` row
        exists for *(participant, path)*, and on POST close ``submittedOn``.

        No-ops when there is no participant in session or the participant
        row was cleared mid-flow.
        """
        if "participantID" not in self.session:
            return

        participant = db.session.get(db.Participant, self.session["participantID"])
        if participant is None:
            return

        participant.lastActiveOn = utcnow_naive()
        db.session.commit()

        progress = db.session.query(db.Progress).filter(
            db.Progress.participantID == self.session["participantID"],
            db.Progress.path == path,
        ).one_or_none()

        if progress is None:
            progress = db.Progress()
            progress.participantID = self.session["participantID"]
            progress.path = path
            progress.startedOn = utcnow_naive()
            db.session.add(progress)
            db.session.commit()

        if request.method == "POST":
            progress.submittedOn = utcnow_naive()
            db.session.commit()

    def close_progress(self, path):
        """Close out the participant's Progress row for *path* by setting
        ``submittedOn`` to now, if it is still NULL. No-op when there's no
        participant in session, no path, or no matching Progress row.
        """
        if not path:
            return
        if "participantID" not in self.session:
            return

        progress = db.session.query(db.Progress).filter(
            db.Progress.participantID == self.session["participantID"],
            db.Progress.path == path,
        ).one_or_none()

        if progress is None or progress.submittedOn is not None:
            return

        progress.submittedOn = utcnow_naive()
        db.session.commit()
