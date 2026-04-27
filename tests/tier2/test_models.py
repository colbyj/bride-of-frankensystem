"""Tier 2 tests for default models (Participant, Progress, RadioGridLog).

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture from conftest.py.
"""

from datetime import datetime, timedelta

import pytest

from tests.conftest import write_questionnaire_file


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


# ===========================================================================
# TestAssignCondition
# ===========================================================================

class TestAssignCondition:
    def test_greedy_balancing(self, bofs_app):
        """Assigns to condition with fewest participants."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        # Seed: 2 in condition 1, 0 in condition 2
        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=1)

        new_p = _make_participant(bofs_app, condition=0)
        new_p.assign_condition()
        bofs_app.db.session.commit()

        assert new_p.condition == 2

    def test_excludes_from_count(self, bofs_app):
        """Participants with excludeFromCount=True not counted."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        # 2 in condition 1, but one is excluded
        _make_participant(bofs_app, condition=1, excludeFromCount=False)
        _make_participant(bofs_app, condition=1, excludeFromCount=True)
        # 1 in condition 2
        _make_participant(bofs_app, condition=2)

        new_p = _make_participant(bofs_app, condition=0)
        new_p.assign_condition()
        bofs_app.db.session.commit()

        # Condition 1 effective count = 1, Condition 2 count = 1 → tie → picks first
        assert new_p.condition == 1

    def test_respects_enabled_flag(self, bofs_app):
        """Disabled conditions are skipped.

        Note: assign_condition uses pCount.index(count) which returns the
        first matching index, so each condition must have a unique count
        for the sorted lookup to resolve correctly.
        """
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": False},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        # A (condition 1) has 0 participants, B (condition 2) has 1
        # Sorted order tries A first (count=0), but it's disabled, then B (count=1)
        _make_participant(bofs_app, condition=2)

        new_p = _make_participant(bofs_app, condition=0)
        new_p.assign_condition()
        bofs_app.db.session.commit()

        # A is disabled, so picks B
        assert new_p.condition == 2

    def test_no_conditions_sets_none(self, bofs_app):
        """No CONDITIONS config → condition=None."""
        bofs_app.config["CONDITIONS"] = []

        new_p = _make_participant(bofs_app, condition=0)
        new_p.assign_condition()
        bofs_app.db.session.commit()

        assert new_p.condition is None


# ===========================================================================
# TestParticipantDuration
# ===========================================================================

class TestParticipantDuration:
    def test_duration_with_times(self, bofs_app):
        p = _make_participant(bofs_app)
        p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        p.timeEnded = datetime(2024, 1, 1, 12, 5, 30)
        bofs_app.db.session.commit()

        assert p.duration == 330.0

    def test_duration_no_end_returns_zero(self, bofs_app):
        p = _make_participant(bofs_app)
        p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        p.timeEnded = None
        bofs_app.db.session.commit()

        assert p.duration == 0

    def test_display_duration_finished(self, bofs_app):
        p = _make_participant(bofs_app)
        p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        p.timeEnded = datetime(2024, 1, 1, 12, 5, 30)
        p.finished = True
        bofs_app.db.session.commit()

        result = p.display_duration()
        assert result == "5:30"


# ===========================================================================
# TestProgressDisplayDuration
# ===========================================================================

class TestProgressDisplayDuration:
    def test_not_submitted_shows_ellipsis(self, bofs_app):
        p = _make_participant(bofs_app)
        prog = bofs_app.db.Progress()
        prog.participantID = p.participantID
        prog.path = "consent"
        prog.startedOn = datetime(2024, 1, 1, 12, 0, 0)
        prog.submittedOn = None
        bofs_app.db.session.add(prog)
        bofs_app.db.session.commit()

        assert prog.display_duration() == "..."

    def test_submitted_shows_formatted_time(self, bofs_app):
        p = _make_participant(bofs_app)
        prog = bofs_app.db.Progress()
        prog.participantID = p.participantID
        prog.path = "survey"
        prog.startedOn = datetime(2024, 1, 1, 12, 0, 0)
        prog.submittedOn = datetime(2024, 1, 1, 12, 2, 15)
        bofs_app.db.session.add(prog)
        bofs_app.db.session.commit()

        # 135 seconds = 2:15
        assert prog.display_duration() == "2:15"


# ===========================================================================
# TestCloseProgressSubmitted — close-out on forward navigation
# ===========================================================================

def _make_progress(app, participant_id, path, submitted_on=None):
    prog = app.db.Progress()
    prog.participantID = participant_id
    prog.path = path
    prog.startedOn = datetime(2024, 1, 1, 12, 0, 0)
    prog.submittedOn = submitted_on
    app.db.session.add(prog)
    app.db.session.commit()
    return prog


class TestCloseProgressSubmitted:
    def test_sets_submitted_on_when_null(self, bofs_app):
        from flask import session
        from BOFS.util import close_progress_submitted

        p = _make_participant(bofs_app)
        prog = _make_progress(bofs_app, p.participantID, "custom_page")

        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            close_progress_submitted("custom_page")

        bofs_app.db.session.refresh(prog)
        assert prog.submittedOn is not None

    def test_does_not_overwrite_existing(self, bofs_app):
        from flask import session
        from BOFS.util import close_progress_submitted

        original = datetime(2024, 1, 1, 12, 0, 30)
        p = _make_participant(bofs_app)
        prog = _make_progress(bofs_app, p.participantID, "custom_page",
                              submitted_on=original)

        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            close_progress_submitted("custom_page")

        bofs_app.db.session.refresh(prog)
        assert prog.submittedOn == original

    def test_no_op_without_participant_in_session(self, bofs_app):
        from BOFS.util import close_progress_submitted

        p = _make_participant(bofs_app)
        prog = _make_progress(bofs_app, p.participantID, "custom_page")

        with bofs_app.test_request_context():
            close_progress_submitted("custom_page")

        bofs_app.db.session.refresh(prog)
        assert prog.submittedOn is None

    def test_no_op_when_no_progress_row(self, bofs_app):
        from flask import session
        from BOFS.util import close_progress_submitted

        p = _make_participant(bofs_app)
        # No Progress row for this path

        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            close_progress_submitted("never_visited")  # should not raise

    def test_no_op_when_path_empty(self, bofs_app):
        from flask import session
        from BOFS.util import close_progress_submitted

        p = _make_participant(bofs_app)
        prog = _make_progress(bofs_app, p.participantID, "")

        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            close_progress_submitted(None)
            close_progress_submitted("")

        bofs_app.db.session.refresh(prog)
        assert prog.submittedOn is None


class TestRedirectAndSetNextPath:
    def test_closes_outgoing_and_advances(self, bofs_app):
        from flask import session
        from BOFS.util import redirect_and_set_next_path

        p = _make_participant(bofs_app)
        outgoing = _make_progress(bofs_app, p.participantID, "consent")

        with bofs_app.test_request_context():
            session['participantID'] = p.participantID
            session['currentUrl'] = "consent"
            response = redirect_and_set_next_path("consent")

        bofs_app.db.session.refresh(outgoing)
        assert outgoing.submittedOn is not None
        assert response.status_code == 302
        # PAGE_LIST in conftest is [consent, end]; next after consent is end.
        assert response.location.endswith("/end")


# ===========================================================================
# TestUpdateParticipantTracking — the helper invoked from before_request_
# ===========================================================================

class TestUpdateParticipantTracking:
    def test_creates_progress_row_when_missing(self, bofs_app):
        from flask import session
        from BOFS.util import update_participant_tracking

        p = _make_participant(bofs_app)
        with bofs_app.test_request_context("/my_custom_page"):
            session['participantID'] = p.participantID
            update_participant_tracking("my_custom_page")

        prog = bofs_app.db.session.query(bofs_app.db.Progress).filter_by(
            participantID=p.participantID, path="my_custom_page"
        ).one()
        assert prog.startedOn is not None
        assert prog.submittedOn is None  # GET, not POST

    def test_refreshes_last_active_on(self, bofs_app):
        from flask import session
        from BOFS.util import update_participant_tracking

        old = datetime(2024, 1, 1, 0, 0, 0)
        p = _make_participant(bofs_app)
        p.lastActiveOn = old
        bofs_app.db.session.commit()

        with bofs_app.test_request_context("/my_custom_page"):
            session['participantID'] = p.participantID
            update_participant_tracking("my_custom_page")

        bofs_app.db.session.refresh(p)
        assert p.lastActiveOn > old

    def test_post_sets_submitted_on(self, bofs_app):
        from flask import session
        from BOFS.util import update_participant_tracking

        p = _make_participant(bofs_app)
        with bofs_app.test_request_context("/my_page", method="POST"):
            session['participantID'] = p.participantID
            update_participant_tracking("my_page")

        prog = bofs_app.db.session.query(bofs_app.db.Progress).filter_by(
            participantID=p.participantID, path="my_page"
        ).one()
        assert prog.submittedOn is not None

    def test_no_op_without_participant(self, bofs_app):
        from BOFS.util import update_participant_tracking

        with bofs_app.test_request_context("/my_page"):
            update_participant_tracking("my_page")  # should not raise

        rows = bofs_app.db.session.query(bofs_app.db.Progress).all()
        assert rows == []

    def test_idempotent_on_second_call(self, bofs_app):
        from flask import session
        from BOFS.util import update_participant_tracking

        p = _make_participant(bofs_app)
        with bofs_app.test_request_context("/my_page"):
            session['participantID'] = p.participantID
            update_participant_tracking("my_page")
            first = bofs_app.db.session.query(bofs_app.db.Progress).filter_by(
                participantID=p.participantID, path="my_page"
            ).one()
            first_started = first.startedOn

            update_participant_tracking("my_page")  # second call
            after = bofs_app.db.session.query(bofs_app.db.Progress).filter_by(
                participantID=p.participantID, path="my_page"
            ).one()
            assert after.startedOn == first_started  # not overwritten


# ===========================================================================
# TestBeforeRequestTracking — before_request_ tracks an undecorated route
# ===========================================================================

class TestBeforeRequestTracking:
    def test_tracks_when_path_matches_currenturl(self, bofs_app):
        from flask import session

        p = _make_participant(bofs_app)
        with bofs_app.test_request_context("/my_custom_page"):
            session['participantID'] = p.participantID
            session['currentUrl'] = "my_custom_page"
            bofs_app.before_request_()

        prog = bofs_app.db.session.query(bofs_app.db.Progress).filter_by(
            participantID=p.participantID, path="my_custom_page"
        ).one_or_none()
        assert prog is not None

    def test_skips_when_path_does_not_match_currenturl(self, bofs_app):
        from flask import session

        p = _make_participant(bofs_app)
        with bofs_app.test_request_context("/wrong_page"):
            session['participantID'] = p.participantID
            session['currentUrl'] = "my_custom_page"
            bofs_app.before_request_()

        rows = bofs_app.db.session.query(bofs_app.db.Progress).all()
        assert rows == []

    def test_skips_admin_path(self, bofs_app):
        from flask import session

        p = _make_participant(bofs_app)
        with bofs_app.test_request_context("/admin/dashboard"):
            session['participantID'] = p.participantID
            session['currentUrl'] = "my_custom_page"
            bofs_app.before_request_()

        rows = bofs_app.db.session.query(bofs_app.db.Progress).all()
        assert rows == []


# ===========================================================================
# TestWarnUndecoratedPages
# ===========================================================================

class TestWarnUndecoratedPages:
    def test_warns_for_undecorated_route(self, bofs_app, caplog):
        from BOFS.util import verify_correct_page

        @verify_correct_page
        def decorated_view():
            return "ok"

        def undecorated_view():
            return "ok"

        bofs_app.add_url_rule("/good_page", endpoint="good_page",
                              view_func=decorated_view)
        bofs_app.add_url_rule("/bad_page", endpoint="bad_page",
                              view_func=undecorated_view)

        # Inject into PAGE_LIST
        bofs_app.page_list.page_list.extend([
            {"name": "Good", "path": "good_page"},
            {"name": "Bad", "path": "bad_page"},
        ])

        with caplog.at_level("WARNING"):
            bofs_app.warn_undecorated_pages()

        msgs = [rec.message for rec in caplog.records]
        assert any("'bad_page'" in m and "missing @verify_correct_page" in m
                   for m in msgs)
        assert not any("'good_page'" in m for m in msgs)

    def test_skips_consent_and_end(self, bofs_app, caplog):
        # PAGE_LIST in conftest is [consent, end] — both in the skip list.
        # consent is served by route_consent_html (no decorator) but it's
        # framework-special, so no warning.
        with caplog.at_level("WARNING"):
            bofs_app.warn_undecorated_pages()

        msgs = [rec.message for rec in caplog.records]
        assert not any("missing @verify_correct_page" in m for m in msgs)

    def test_warns_for_unrouted_path(self, bofs_app, caplog):
        bofs_app.page_list.page_list.append(
            {"name": "Phantom", "path": "this_page_does_not_exist"}
        )

        with caplog.at_level("WARNING"):
            bofs_app.warn_undecorated_pages()

        msgs = [rec.message for rec in caplog.records]
        assert any("'this_page_does_not_exist'" in m and "doesn't match" in m
                   for m in msgs)

    def test_suppress_activity_polling_implies_manual_route(self, bofs_app, caplog):
        # @suppress_activity_polling signals the researcher is managing the
        # route manually, so missing @verify_correct_page is not a mistake.
        from BOFS.util import suppress_activity_polling

        @suppress_activity_polling
        def manual_view():
            return "ok"

        bofs_app.add_url_rule("/manual_page", endpoint="manual_page",
                              view_func=manual_view)
        bofs_app.page_list.page_list.append(
            {"name": "Manual", "path": "manual_page"}
        )

        with caplog.at_level("WARNING"):
            bofs_app.warn_undecorated_pages()

        msgs = [rec.message for rec in caplog.records]
        assert not any("'manual_page'" in m and "missing @verify_correct_page" in m
                       for m in msgs)


# ===========================================================================
# TestQuestionnaireLog
# ===========================================================================

GRID_QUESTIONNAIRE = {
    "title": "Grid",
    "instructions": "",
    "questions": [
        {
            "questiontype": "radiogrid",
            "id": "grid",
            "labels": ["1", "2", "3"],
            "q_text": [
                {"id": "g_q1", "text": "Item one"},
                {"id": "g_q2", "text": "Item two"},
            ],
        }
    ],
}


class TestQuestionnaireLog:
    def test_returns_time_deltas(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "log_grid", GRID_QUESTIONNAIRE)
        p = _make_participant(bofs_app)

        # Create a questionnaire record for this participant
        record = q.db_class()
        record.participantID = p.participantID
        record.tag = ""
        record.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        record.timeEnded = datetime(2024, 1, 1, 12, 1, 0)
        record.g_q1 = 2
        record.g_q2 = 3
        bofs_app.db.session.add(record)

        # Create log entries
        log1 = bofs_app.db.RadioGridLog()
        log1.participantID = p.participantID
        log1.questionnaire = "log_grid"
        log1.tag = 0  # empty tag stored as 0
        log1.questionID = "g_q1"
        log1.timeClicked = datetime(2024, 1, 1, 12, 0, 5)
        log1.value = "2"

        log2 = bofs_app.db.RadioGridLog()
        log2.participantID = p.participantID
        log2.questionnaire = "log_grid"
        log2.tag = 0
        log2.questionID = "g_q2"
        log2.timeClicked = datetime(2024, 1, 1, 12, 0, 8)
        log2.value = "3"

        bofs_app.db.session.add_all([log1, log2])
        bofs_app.db.session.commit()

        result = p.questionnaire_log("log_grid")

        # First delta: timeClicked(g_q1) - timeStarted = 5 seconds
        assert result["g_q1"] == pytest.approx(5.0)
        # Second delta: timeClicked(g_q2) - timeClicked(g_q1) = 3 seconds
        assert result["g_q2"] == pytest.approx(3.0)

    def test_empty_logs_returns_empty_dict(self, bofs_app):
        q = write_questionnaire_file(bofs_app, "empty_log", GRID_QUESTIONNAIRE)
        p = _make_participant(bofs_app)

        # Create a questionnaire record but no logs
        record = q.db_class()
        record.participantID = p.participantID
        record.tag = ""
        record.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        record.timeEnded = datetime(2024, 1, 1, 12, 1, 0)
        record.g_q1 = 0
        record.g_q2 = 0
        bofs_app.db.session.add(record)
        bofs_app.db.session.commit()

        result = p.questionnaire_log("empty_log")
        assert result == {}

    def test_tag_normalization(self, bofs_app):
        """Empty tag is treated as '0' in the query, matching tag=0 in DB."""
        q = write_questionnaire_file(bofs_app, "tag_log", GRID_QUESTIONNAIRE)
        p = _make_participant(bofs_app)

        # Record with tag="0" (how empty tags are stored)
        record = q.db_class()
        record.participantID = p.participantID
        record.tag = "0"
        record.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
        record.timeEnded = datetime(2024, 1, 1, 12, 1, 0)
        record.g_q1 = 1
        record.g_q2 = 2
        bofs_app.db.session.add(record)

        log1 = bofs_app.db.RadioGridLog()
        log1.participantID = p.participantID
        log1.questionnaire = "tag_log"
        log1.tag = 0
        log1.questionID = "g_q1"
        log1.timeClicked = datetime(2024, 1, 1, 12, 0, 3)
        log1.value = "1"
        bofs_app.db.session.add(log1)
        bofs_app.db.session.commit()

        # Passing tag="" should normalize to 0 and find the log
        result = p.questionnaire_log("tag_log", tag="")
        assert "g_q1" in result
        assert result["g_q1"] == pytest.approx(3.0)
