"""Tier 2 tests for default models (Participant, Progress, QuestionnaireInteraction).

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture from conftest.py.
"""

from datetime import datetime


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

    def test_commits_inside_lock(self, bofs_app):
        """assign_condition must commit the participant row before returning.

        The race-condition fix relies on the in-lock commit: a sibling request
        session calling balancer_counts next must see this row. Without the
        commit (or with only a flush), the next call wouldn't see it and
        both consents would pick the same condition.
        """
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        new_p = bofs_app.db.Participant()
        new_p.ipAddress = "127.0.0.1"
        new_p.userAgent = "test-agent"
        new_p.assign_condition()

        # Row must already be persisted (autoincrement PK populated).
        assert new_p.participantID is not None, (
            "assign_condition did not commit the participant inside the lock"
        )

        # And visible via a separate query.
        found = bofs_app.db.session.query(bofs_app.db.Participant).filter_by(
            participantID=new_p.participantID
        ).first()
        assert found is not None
        assert found.condition in (1, 2)

    def test_serial_calls_pick_distinct_conditions(self, bofs_app):
        """Two consecutive consents — with the in-lock commit, the second call
        sees the first one in balancer_counts and picks the other condition.
        """
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        p1 = bofs_app.db.Participant()
        p1.ipAddress = "127.0.0.1"
        p1.userAgent = "ua"
        p1.assign_condition()

        p2 = bofs_app.db.Participant()
        p2.ipAddress = "127.0.0.1"
        p2.userAgent = "ua"
        p2.assign_condition()

        assert {p1.condition, p2.condition} == {1, 2}, (
            f"second consent did not see first one's row "
            f"(got {p1.condition!r} / {p2.condition!r})"
        )


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
# TestQuestionnaireInteractions
# ===========================================================================

# ===========================================================================
# TestExternalIDSynonym — mTurkID is a SQLAlchemy synonym for externalID
# (back-compat for code written before the rename).
# ===========================================================================

class TestExternalIDSynonym:
    def test_write_via_either_reads_via_either(self, bofs_app):
        p = _make_participant(bofs_app, mTurkID="ABC")
        # Writing via the legacy name is visible via the canonical attribute.
        assert p.externalID == "ABC"
        # And vice versa.
        p.externalID = "XYZ"
        bofs_app.db.session.commit()
        assert p.mTurkID == "XYZ"

    def test_filter_by_either_name_matches_same_row(self, bofs_app):
        _make_participant(bofs_app, mTurkID="TARGET")
        _make_participant(bofs_app, mTurkID="OTHER")

        via_legacy = bofs_app.db.session.query(bofs_app.db.Participant).filter_by(
            mTurkID="TARGET"
        ).all()
        via_canonical = bofs_app.db.session.query(bofs_app.db.Participant).filter_by(
            externalID="TARGET"
        ).all()

        assert len(via_legacy) == 1
        assert len(via_canonical) == 1
        assert via_legacy[0].participantID == via_canonical[0].participantID

    def test_class_attribute_equality_produces_same_sql(self, bofs_app):
        # The class-level attribute access should resolve through the synonym
        # to the same InstrumentedAttribute, producing identical SQL.
        from sqlalchemy import select
        canonical_sql = str(
            select(bofs_app.db.Participant).where(
                bofs_app.db.Participant.externalID == "X"
            ).compile(compile_kwargs={"literal_binds": True})
        )
        legacy_sql = str(
            select(bofs_app.db.Participant).where(
                bofs_app.db.Participant.mTurkID == "X"
            ).compile(compile_kwargs={"literal_binds": True})
        )
        assert canonical_sql == legacy_sql
        # And the column it references is `external_id`, not `mTurkID`.
        assert "external_id" in canonical_sql

    def test_db_column_name_is_external_id(self, bofs_app):
        from sqlalchemy import inspect as sa_inspect
        cols = {c['name'] for c in sa_inspect(bofs_app.db.engine).get_columns('participant')}
        assert 'external_id' in cols
        assert 'mTurkID' not in cols  # only the canonical DB name exists


# ===========================================================================
# TestCheckAndRenameColumn — the dialect-aware migration helper.
# ===========================================================================

class TestCheckAndRenameColumn:
    def _make_test_table(self, app, columns_sql: str):
        """Create a throwaway table with the given columns DDL."""
        with app.db.engine.begin() as conn:
            conn.execute(app.db.DDL(
                f"CREATE TABLE test_rename_target ({columns_sql})"
            ))

    def _columns(self, app):
        from sqlalchemy import inspect as sa_inspect
        return {
            c['name']
            for c in sa_inspect(app.db.engine).get_columns('test_rename_target')
        }

    def test_renames_when_only_old_exists(self, bofs_app):
        from BOFS.admin.util import check_and_rename_column
        self._make_test_table(bofs_app, "id INTEGER PRIMARY KEY, mTurkID TEXT")

        assert check_and_rename_column(
            'test_rename_target', 'mTurkID', 'external_id'
        ) is True
        cols = self._columns(bofs_app)
        assert 'external_id' in cols
        assert 'mTurkID' not in cols

    def test_noop_when_new_already_exists(self, bofs_app):
        from BOFS.admin.util import check_and_rename_column
        self._make_test_table(bofs_app, "id INTEGER PRIMARY KEY, external_id TEXT")

        # Already-renamed schema — no-op, no error.
        assert check_and_rename_column(
            'test_rename_target', 'mTurkID', 'external_id'
        ) is False
        assert 'external_id' in self._columns(bofs_app)

    def test_noop_when_neither_exists(self, bofs_app):
        from BOFS.admin.util import check_and_rename_column
        self._make_test_table(bofs_app, "id INTEGER PRIMARY KEY, other TEXT")

        # Nothing to rename, nothing to error on.
        assert check_and_rename_column(
            'test_rename_target', 'mTurkID', 'external_id'
        ) is False

    def test_preserves_data(self, bofs_app):
        from sqlalchemy import text
        from BOFS.admin.util import check_and_rename_column
        self._make_test_table(bofs_app, "id INTEGER PRIMARY KEY, mTurkID TEXT")
        with bofs_app.db.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO test_rename_target (id, mTurkID) VALUES (1, 'PRE_VALUE')"
            ))

        check_and_rename_column('test_rename_target', 'mTurkID', 'external_id')

        with bofs_app.db.engine.begin() as conn:
            row = conn.execute(text(
                "SELECT external_id FROM test_rename_target WHERE id = 1"
            )).first()
        assert row is not None
        assert row[0] == 'PRE_VALUE'


# ===========================================================================
# TestQuestionnaireInteractions
# ===========================================================================

class TestQuestionnaireInteractions:
    def test_questionnaire_interactions_helper_returns_ordered_events(self, bofs_app):
        p = _make_participant(bofs_app)
        # Two questionnaires; helper must filter by name+tag and order by timestamp.
        rows = [
            ("survey", 0, "q1", "focus", datetime(2024, 1, 1, 12, 0, 1), ""),
            ("survey", 0, "q1", "change", datetime(2024, 1, 1, 12, 0, 5), "hello"),
            ("survey", 0, "q1", "blur", datetime(2024, 1, 1, 12, 0, 8), "hello"),
            ("other", 0, "q1", "change", datetime(2024, 1, 1, 12, 0, 6), "ignored"),
            ("survey", "v2", "q1", "change", datetime(2024, 1, 1, 12, 0, 7), "tagged"),
        ]
        for name, tag, qid, etype, ts, val in rows:
            r = bofs_app.db.QuestionnaireInteraction()
            r.participantID = p.participantID
            r.questionnaire = name
            r.tag = tag
            r.questionID = qid
            r.eventType = etype
            r.timestamp = ts
            r.value = val
            bofs_app.db.session.add(r)
        bofs_app.db.session.commit()

        result = p.questionnaire_interactions("survey")
        assert [r.eventType for r in result] == ["focus", "change", "blur"]
        assert all(r.questionnaire == "survey" and r.tag == "0" for r in result)

        tagged = p.questionnaire_interactions("survey", tag="v2")
        assert len(tagged) == 1
        assert tagged[0].value == "tagged"
