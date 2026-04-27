from urllib.parse import urlsplit
import datetime

from flask import current_app, redirect, request, session

from BOFS.globals import db


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

    # ----- Progress tracking -------------------------------------------

    def track_progress(self, path):
        """Refresh ``Participant.lastActiveOn``, ensure a ``Progress`` row
        exists for *(participant, path)*, and on POST close ``submittedOn``.

        No-ops when there is no participant in session or the participant
        row was cleared mid-flow.
        """
        if "participantID" not in self.session:
            return

        participant = db.session.query(db.Participant).get(self.session["participantID"])
        if participant is None:
            return

        participant.lastActiveOn = datetime.datetime.utcnow()
        db.session.commit()

        progress = db.session.query(db.Progress).filter(
            db.Progress.participantID == self.session["participantID"],
            db.Progress.path == path,
        ).one_or_none()

        if progress is None:
            progress = db.Progress()
            progress.participantID = self.session["participantID"]
            progress.path = path
            progress.startedOn = datetime.datetime.utcnow()
            db.session.add(progress)
            db.session.commit()

        if request.method == "POST":
            progress.submittedOn = datetime.datetime.utcnow()
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

        progress.submittedOn = datetime.datetime.utcnow()
        db.session.commit()
