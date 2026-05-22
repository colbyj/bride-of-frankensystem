from flask import session, request, current_app
from BOFS.globals import db
from BOFS.services.brute_force import get_client_ip
from BOFS.util import (
    utcnow_naive, float_or_0, int_or_0, get_external_id_from_session,
)
import uuid


class ParticipantService:
    """Stateless service for Participant lifecycle and condition assignment."""

    @staticmethod
    def provide_consent(assign_condition: bool = True, log_display_size: bool = False):
        """Create a Participant, optionally assign a condition, commit, write session keys.
        Returns the Participant. Must be called inside a request context.
        """
        p = db.Participant()
        p.ipAddress = get_client_ip()
        p.userAgent = request.user_agent.string
        p.timeStarted = utcnow_naive()
        p.check_useragent_for_crawler()

        # Persist the URL-captured external ID and recruitment source onto
        # the participant row. Without this, ?PROLIFIC_PID= sits in the
        # session but never lands on the participant — every Prolific study
        # would have to include /external_id in PAGE_LIST just to commit it.
        ext_id = get_external_id_from_session()
        if ext_id:
            p.externalID = ext_id
        if session.get('source'):
            p.source = session['source']

        if current_app.config['STATIC_COMPLETION_CODE'] is not None:
            p.code = current_app.config['STATIC_COMPLETION_CODE']
            session['code'] = p.code
        elif current_app.config['GENERATE_COMPLETION_CODE']:
            p.code = uuid.uuid4().hex
            session['code'] = p.code

        if assign_condition:
            if ParticipantService.use_debug_picker():
                # Debug mode defers assignment to /debug_pick_condition. Caller must
                # redirect there before the participant proceeds.
                p.condition = 0
            else:
                p.assign_condition()
        else:
            p.condition = 0

        db.session.add(p)
        db.session.commit()

        session['participantID'] = p.participantID
        session['condition'] = p.condition

        if log_display_size:
            # Display columns are typed (Float for dppx, Integer for the
            # pixel dimensions). request.form returns raw strings, so coerce
            # explicitly; a missing/blank value becomes 0 rather than
            # exploding on commit (which would leave an orphan Participant
            # with no Display row).
            entry = db.Display()
            entry.participantID = session['participantID']
            entry.dppx         = float_or_0(request.form.get('dppx'))
            entry.screenWidth  = int_or_0(request.form.get('screenWidth'))
            entry.screenHeight = int_or_0(request.form.get('screenHeight'))
            entry.innerWidth   = int_or_0(request.form.get('innerWidth'))
            entry.innerHeight  = int_or_0(request.form.get('innerHeight'))

            db.session.add(entry)
            db.session.commit()

        return p

    @staticmethod
    def assign_condition_organic(p) -> None:
        """Run the balancer to pick a condition for *p*, commit, and write session['condition'].
        Wraps Participant.assign_condition() (which mutates p.condition in-place).
        """
        p.assign_condition()
        db.session.commit()
        session['condition'] = p.condition

    @staticmethod
    def assign_condition_explicit(p, condition_num: int) -> None:
        """Set p.condition to *condition_num*, commit, and write session['condition'].
        Used by the debug picker and the explicit /assign_condition route.
        """
        p.condition = condition_num
        db.session.commit()
        session['condition'] = p.condition

    @staticmethod
    def clear_condition(p) -> None:
        """Set p.condition to None and commit. Used during session recovery to
        prevent the orphaned (current) participant from skewing balancer counts.
        """
        p.condition = None
        db.session.commit()

    @staticmethod
    def balancer_counts():
        """Return per-condition participant counts. Delegates to db.Participant."""
        return db.Participant.balancer_counts()

    @staticmethod
    def compute_organic_condition():
        """Return the condition the balancer would pick now, or None. Delegates to db.Participant."""
        return db.Participant.compute_organic_condition()

    @staticmethod
    def current_condition():
        """Read the participant's current condition from the session. Returns int|None.
        Honors the session quirk where -1 maps to 0; returns None if no request context.
        """
        try:
            # If session exists, and condition is a key, then let's grab the current condition!
            if not session is None and 'condition' in session:
                condition = session['condition']
                if condition == -1:
                    condition = 0
                return int(condition)
            return 0
        except RuntimeError:
            # "Working outside of request context" — caller invoked us from
            # a CLI or background thread. Return None so the caller can
            # detect "no participant context available".
            return None

    @staticmethod
    def condition_count() -> int:
        """Return len(current_app.config['CONDITIONS'])."""
        return len(current_app.config["CONDITIONS"])

    @staticmethod
    def all_conditions_disabled() -> bool:
        """True iff CONDITIONS is non-empty AND every condition has enabled=False."""
        conditions = current_app.config.get('CONDITIONS', [])
        if not conditions:
            return False
        return not any(c.get('enabled', True) for c in conditions)

    @staticmethod
    def use_debug_picker() -> bool:
        """True iff the dev should be sent to /debug_pick_condition before assignment.
        Requires debug mode AND at least one configured condition — with zero conditions
        the picker renders no rows and the participant can't proceed.
        """
        return (
            current_app.run_with_debugging
            and len(current_app.config.get('CONDITIONS', [])) > 0
        )

    @staticmethod
    def toggle_condition_enabled(condition_idx: int) -> bool:
        """Flip the 'enabled' flag for `current_app.config['CONDITIONS'][condition_idx]`.

        Takes a 0-based index. Caller is responsible for range-checking;
        out-of-bounds indices raise IndexError. Returns the new value of
        the flag.
        """
        meta = current_app.config['CONDITIONS'][condition_idx]
        meta['enabled'] = not meta.get('enabled', True)
        return meta['enabled']

    @staticmethod
    def max_assigned_condition_db():
        """Max condition value present in the participant table. Useful post-collection.
        Replaces util.fetch_condition_count_db.
        """
        return db.session.query(db.func.max(db.Participant.condition)).one()[0]
