"""Service for restoring a participant's prior session by mTurk/external ID."""

from typing import Optional

from flask import session, current_app

from BOFS.globals import db
from BOFS.BOFSSession import BOFSSessionInterface
from BOFS.services.participant import ParticipantService


class SessionRecoveryService:
    """Restore a participant's prior session by mTurk/external ID, when configured."""

    _LOOP_BLOCKED_PATHS = ('startMTurk', 'start_mturk', 'external_id', 'consent')

    @staticmethod
    def try_restore(p, mturk_id: str) -> Optional[str]:
        """
        Attempt to restore a prior session for *mturk_id*.

        Behavior, in order:
          1. If RETRIEVE_SESSIONS is False → return None (no recovery).
          2. Look up SessionStore rows with matching mTurkID and a different
             participantID, ordered most-recent first.
          3. If none → return None.
          4. Look up the matching past Participant; with ALLOW_RETAKES=True,
             skip finished attempts.
          5. If a usable past Participant exists:
               - Deserialize the past session blob and merge keys into the
                 current session.
               - Clear the current participant's condition (orphan handling).
               - Restore session['condition'] from any past Participant whose
                 condition is non-zero and non-None.
               - If past session had a 'currentUrl' that's safe (not in the
                 loop-blocked set), return it as the redirect URL.
          6. Otherwise return None.

        Returns the URL to redirect to (e.g. "questionnaire/survey"), or None
        if no recovery happened or the recovered URL would cause a loop. The
        caller is responsible for the final redirect (including the
        non-recovery fallback to /redirect_from_page/...).
        """
        if not current_app.config['RETRIEVE_SESSIONS']:
            return None

        session_rows = SessionRecoveryService._find_past_session_rows(mturk_id, p.participantID)

        allow_retakes = current_app.config['ALLOW_RETAKES']

        if session_rows and len(session_rows) > 0:
            past_participants = SessionRecoveryService._matching_past_participants(
                mturk_id,
                session_rows[0].participantID,
                p.participantID,
                allow_retakes,
            )

            if past_participants and len(past_participants) > 0:
                # Deserialise without writing to the live session yet — if the
                # recovered ``currentUrl`` would land on a page that just
                # blocked the participant, merging it in first would clobber
                # the existing ``session['currentUrl']`` and verify_correct_page
                # would redirect them straight back to the blocked URL.
                dict_data = BOFSSessionInterface.serializer.loads(session_rows[0].data)
                recovered_url = dict_data.get('currentUrl')
                if recovered_url and recovered_url in SessionRecoveryService._LOOP_BLOCKED_PATHS:
                    return None

                SessionRecoveryService._apply_session_dict(dict_data)
                ParticipantService.clear_condition(p)
                SessionRecoveryService._restore_condition(past_participants)

                if recovered_url:
                    return recovered_url

        return None

    @staticmethod
    def _find_past_session_rows(mturk_id: str, current_pid: int):
        """SessionStore rows for mturk_id excluding the current participant, newest first."""
        return (
            db.session.query(db.SessionStore)
            .filter(
                db.SessionStore.mTurkID == mturk_id,
                db.SessionStore.participantID != current_pid,
            )
            .order_by(db.desc(db.SessionStore.createdOn))
            .all()
        )

    @staticmethod
    def _matching_past_participants(mturk_id: str, sessionstore_pid: int, current_pid: int, allow_retakes: bool):
        """Past Participants matching mturk_id and the chosen SessionStore's pid.
        With allow_retakes=True, also excludes finished attempts and the current pid.
        """
        query = db.session.query(db.Participant).filter(
            db.Participant.mTurkID == mturk_id,
            db.Participant.participantID == sessionstore_pid,
        )

        if allow_retakes:
            # Note: uses session['participantID'] to mirror the original route exactly.
            query = query.filter(
                db.Participant.finished != True,
                db.Participant.participantID != session['participantID'],
            )

        return query.all()

    @staticmethod
    def _apply_session_dict(dict_data: dict) -> None:
        """Write each key from a pre-deserialised SessionStore.data dict into
        the live Flask session. Callers that need to make decisions based on
        the recovered URL should inspect ``dict_data`` themselves before
        invoking this — once it runs, ``session['currentUrl']`` reflects the
        recovered value."""
        for key in dict_data.keys():
            session[key] = dict_data[key]

    @staticmethod
    def _restore_condition(past_participants) -> None:
        """Iterate past_participants; if any has a non-zero, non-None condition,
        write it to session['condition']. Mirrors the loop in views.py."""
        for past_attempt in past_participants:
            if past_attempt.condition != 0 and past_attempt.condition is not None:
                session['condition'] = past_attempt.condition
