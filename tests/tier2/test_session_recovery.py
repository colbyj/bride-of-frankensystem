"""Tier 2 tests for SessionRecoveryService.

Tests edge cases not covered by the existing tier3 integration tests.
All tests use the ``bofs_app`` fixture (in-memory SQLite, app context pushed).
"""

import datetime

import pytest

from BOFS.BOFSSession import BOFSSessionInterface
from BOFS.services.session_recovery import SessionRecoveryService
from BOFS.util import utcnow_naive


# ===========================================================================
# Helpers
# ===========================================================================

def _make_participant(app, **kwargs):
    """Create a Participant with sensible defaults, overridden by kwargs."""
    defaults = dict(
        mTurkID="",
        ipAddress="127.0.0.1",
        userAgent="test-agent",
        condition=0,
        finished=False,
        excludeFromCount=False,
    )
    defaults.update(kwargs)
    p = app.db.Participant()
    for k, v in defaults.items():
        setattr(p, k, v)
    app.db.session.add(p)
    app.db.session.commit()
    return p


def _make_session_store(app, participant, mturk_id, data_dict):
    """Create a SessionStore row with serialized data for *participant*.

    Sets expiry ~21 days in the future and createdOn 1 hour ago so
    ordering by createdOn yields deterministic results.
    """
    ss = app.db.SessionStore()
    ss.sessionID = f"test-session-{participant.participantID}"
    ss.participantID = participant.participantID
    ss.mTurkID = mturk_id
    ss.data = BOFSSessionInterface.serializer.dumps(data_dict)
    ss.expiry = utcnow_naive() + datetime.timedelta(days=21)
    ss.createdOn = utcnow_naive() - datetime.timedelta(hours=1)
    app.db.session.add(ss)
    app.db.session.commit()
    return ss


# ===========================================================================
# Tests
# ===========================================================================

class TestSessionRecoveryService:

    def test_returns_none_when_retrieve_sessions_disabled(self, bofs_app):
        """RETRIEVE_SESSIONS=False → try_restore returns None; p.condition unchanged."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = False
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='X', condition=1)
            past_p = _make_participant(app, mTurkID='X', condition=2, finished=True)
            _make_session_store(app, past_p, 'X', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'X')

        assert result is None
        # Condition must be untouched
        app.db.session.expire_all()
        assert current_p.condition == 1

    def test_returns_none_when_no_past_sessions(self, bofs_app):
        """RETRIEVE_SESSIONS=True; no SessionStore rows → returns None."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='Y', condition=1)
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'Y')

        assert result is None

    def test_returns_none_when_past_session_has_same_participant_id(self, bofs_app):
        """SessionStore row with same participantID as current p is excluded by the query."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='Z', condition=1)
            # SessionStore row intentionally uses the *same* participantID
            _make_session_store(app, current_p, 'Z', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': current_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'Z')

        assert result is None

    def test_restores_session_data_into_flask_session(self, bofs_app):
        """Past session data is merged into the Flask session on recovery."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W1', condition=0)
            past_p = _make_participant(app, mTurkID='W1', condition=2, finished=False)
            _make_session_store(app, past_p, 'W1', {
                'foo': 'bar',
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            SessionRecoveryService.try_restore(current_p, 'W1')

            assert session['foo'] == 'bar'
            assert session['condition'] == 2

    def test_clears_current_participant_condition(self, bofs_app):
        """p.condition is set to None after successful recovery."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W2', condition=1)
            past_p = _make_participant(app, mTurkID='W2', condition=2, finished=False)
            _make_session_store(app, past_p, 'W2', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            SessionRecoveryService.try_restore(current_p, 'W2')

        app.db.session.expire_all()
        assert current_p.condition is None

    def test_returns_currenturl_for_safe_redirect(self, bofs_app):
        """Returns 'questionnaire/survey' when past currentUrl is safe."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W3', condition=0)
            past_p = _make_participant(app, mTurkID='W3', condition=2, finished=False)
            _make_session_store(app, past_p, 'W3', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'W3')

        assert result == 'questionnaire/survey'

    def test_loop_blocked_currenturl_returns_none(self, bofs_app):
        """Past currentUrl 'consent' is blocked; try_restore returns None."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W4', condition=0)
            past_p = _make_participant(app, mTurkID='W4', condition=2, finished=False)
            _make_session_store(app, past_p, 'W4', {
                'condition': 2,
                'currentUrl': 'consent',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'W4')

        assert result is None

    def test_allow_retakes_skips_finished_past_participant(self, bofs_app):
        """ALLOW_RETAKES=True with finished=True past attempt → no recovery."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = True

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W5', condition=1)
            past_p = _make_participant(app, mTurkID='W5', condition=2, finished=True)
            _make_session_store(app, past_p, 'W5', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'W5')

        assert result is None
        # condition must not be cleared
        app.db.session.expire_all()
        assert current_p.condition == 1

    def test_allow_retakes_false_restores_finished_past(self, bofs_app):
        """ALLOW_RETAKES=False restores even finished past attempts."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W6', condition=0)
            past_p = _make_participant(app, mTurkID='W6', condition=2, finished=True)
            _make_session_store(app, past_p, 'W6', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'W6')

        assert result == 'questionnaire/survey'
        app.db.session.expire_all()
        assert current_p.condition is None

    def test_condition_restored_from_non_zero_past(self, bofs_app):
        """session['condition'] is overwritten with the non-zero condition from a past attempt."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W7', condition=0)
            past_p = _make_participant(app, mTurkID='W7', condition=2, finished=False)
            _make_session_store(app, past_p, 'W7', {
                'condition': 2,
                'currentUrl': 'questionnaire/survey',
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            SessionRecoveryService.try_restore(current_p, 'W7')

            assert session['condition'] == 2

    def test_no_currenturl_in_past_session_returns_none(self, bofs_app):
        """No 'currentUrl' in past session → restoration happens but try_restore returns None."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID='W8', condition=1)
            past_p = _make_participant(app, mTurkID='W8', condition=2, finished=False)
            _make_session_store(app, past_p, 'W8', {
                'foo': 'baz',
                'condition': 2,
                # no 'currentUrl' key
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, 'W8')

            # Session was merged despite no currentUrl
            assert session.get('foo') == 'baz'
            assert session['condition'] == 2

        # p.condition cleared (restoration did happen)
        app.db.session.expire_all()
        assert current_p.condition is None

        # But redirect URL is None
        assert result is None

    # ------------------------------------------------------------------
    # Additional edge-case: all loop-blocked paths are actually blocked
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("blocked_url", [
        'startMTurk', 'start_mturk', 'external_id', 'consent'
    ])
    def test_all_loop_blocked_paths_return_none(self, bofs_app, blocked_url):
        """Every path in _LOOP_BLOCKED_PATHS triggers the loop-prevention guard."""
        app = bofs_app
        app.config['RETRIEVE_SESSIONS'] = True
        app.config['ALLOW_RETAKES'] = False

        with app.test_request_context('/'):
            from flask import session
            current_p = _make_participant(app, mTurkID=f'BL-{blocked_url}', condition=0)
            past_p = _make_participant(app, mTurkID=f'BL-{blocked_url}', condition=2, finished=False)
            _make_session_store(app, past_p, f'BL-{blocked_url}', {
                'condition': 2,
                'currentUrl': blocked_url,
                'participantID': past_p.participantID,
            })
            session['participantID'] = current_p.participantID

            result = SessionRecoveryService.try_restore(current_p, f'BL-{blocked_url}')

        assert result is None
