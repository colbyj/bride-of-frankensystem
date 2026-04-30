"""Tier 2 tests for AdminStatsService.

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app_with_questionnaires`` fixture from conftest.py which
provides: consent → questionnaire/survey → questionnaire/survey/before → end,
and CONDITIONS = [Control, Treatment].
"""

from datetime import datetime

import pytest

from BOFS.services.admin_stats import AdminStatsService


# ===========================================================================
# Helpers
# ===========================================================================

def _make_participant(app, **kwargs):
    """Create a Participant with sensible defaults, overridden by kwargs."""
    defaults = dict(
        mTurkID="",
        ipAddress="127.0.0.1",
        userAgent="test-agent",
        condition=1,
        finished=False,
        excludeFromCount=False,
        isCrawler=False,
        lastActiveOn=datetime(2024, 1, 1, 12, 0, 0),
        timeStarted=datetime(2024, 1, 1, 12, 0, 0),
    )
    defaults.update(kwargs)
    p = app.db.Participant()
    for k, v in defaults.items():
        setattr(p, k, v)
    app.db.session.add(p)
    app.db.session.commit()
    return p


def _make_progress(app, participant, path, started=None, submitted=None):
    prog = app.db.Progress()
    prog.participantID = participant.participantID
    prog.path = path
    prog.startedOn = started or datetime(2024, 1, 1, 12, 0, 0)
    prog.submittedOn = submitted
    app.db.session.add(prog)
    app.db.session.commit()
    return prog


# ===========================================================================
# Tests for fetch_progress
# ===========================================================================

class TestFetchProgress:
    def test_fetch_progress_excludes_consent_and_end(self, bofs_app_with_questionnaires):
        """Returned pages list does NOT include 'consent' or 'end' paths."""
        app = bofs_app_with_questionnaires
        pages, _ = AdminStatsService.fetch_progress()

        paths = [p['path'] for p in pages]
        assert 'consent' not in paths
        assert 'end' not in paths

    def test_fetch_progress_excludes_crawlers(self, bofs_app_with_questionnaires):
        """Progress list includes only non-crawler participants."""
        app = bofs_app_with_questionnaires
        _make_participant(app, isCrawler=False)
        _make_participant(app, isCrawler=True)

        _, progress = AdminStatsService.fetch_progress()

        # Each row is a tuple: (Participant, Progress|None, ...)
        # The Participant is always the first element.
        participant_ids = [row[0].participantID for row in progress]
        crawlers = [row[0] for row in progress if row[0].isCrawler]
        assert len(crawlers) == 0
        assert len(participant_ids) == 1

    def test_fetch_progress_returns_one_row_per_participant(self, bofs_app_with_questionnaires):
        """One result row per participant even when no Progress rows exist."""
        app = bofs_app_with_questionnaires
        _make_participant(app)
        _make_participant(app)
        _make_participant(app)

        _, progress = AdminStatsService.fetch_progress()
        assert len(progress) == 3

    def test_fetch_progress_filters_adjacent_removable_pages(self, bofs_app_with_questionnaires, monkeypatch):
        """Adjacent 'consent'/'end' entries are both removed.

        Regression guard for the prior `pages.remove(page)` mid-iteration bug,
        which would skip the element after each removed element. With two
        adjacent removable entries, the second one would have survived.
        """
        app = bofs_app_with_questionnaires
        custom = [
            {'name': 'Consent', 'path': 'consent'},
            {'name': 'Consent2', 'path': 'consent'},
            {'name': 'Survey', 'path': 'questionnaire/survey'},
            {'name': 'End1', 'path': 'end'},
            {'name': 'End2', 'path': 'end'},
        ]
        monkeypatch.setattr(app.page_list, 'flat_page_list',
                            lambda condition=None, participant_id=None: list(custom))

        pages, _ = AdminStatsService.fetch_progress()
        paths = [p['path'] for p in pages]

        assert paths == ['questionnaire/survey']

    def test_fetch_progress_includes_progress_entities(self, bofs_app_with_questionnaires):
        """A seeded Progress row appears at the correct column in the result tuple."""
        app = bofs_app_with_questionnaires
        p = _make_participant(app)
        _make_progress(app, p, 'questionnaire/survey')

        pages, progress = AdminStatsService.fetch_progress()

        # Find the index of 'questionnaire/survey' in pages
        page_paths = [pg['path'] for pg in pages]
        assert 'questionnaire/survey' in page_paths
        survey_idx = page_paths.index('questionnaire/survey')

        assert len(progress) == 1
        row = progress[0]
        # Row layout: (Participant, prog_for_page0, prog_for_page1, ...)
        # So progress entity for page at survey_idx is at position survey_idx + 1
        prog_entity = row[survey_idx + 1]
        assert prog_entity is not None
        assert prog_entity.path == 'questionnaire/survey'
        assert prog_entity.participantID == p.participantID

    def test_fetch_progress_ignores_show_if_predicates(
        self, bofs_app_with_questionnaires, monkeypatch
    ):
        """The progress table must show every page that any participant could
        have visited, including pages gated by a ``show_if`` predicate that
        would currently evaluate to False against the admin's own session
        data. Regression guard for the bug where ``flat_page_list()`` with
        no args picked up ``participantID`` from the admin's session and
        filtered hidden pages out of the table.
        """
        app = bofs_app_with_questionnaires

        # Compile a fake AST that always evaluates to False — no questionnaires
        # match, so any predicate evaluation would hide the page.
        custom = [
            {'name': 'Consent', 'path': 'consent'},
            {'name': 'Always Visible', 'path': 'questionnaire/survey'},
            {'name': 'Branched Out', 'path': 'questionnaire/branched',
             '_show_if_ast': {'op': '==',
                              'args': [{'const': 1}, {'const': 0}]},
             '_show_if_refs': {}},
            {'name': 'End', 'path': 'end'},
        ]
        monkeypatch.setattr(app.page_list, 'page_list', custom)

        # Even with a session participant_id set (simulating the admin
        # having tested as a participant earlier), the progress table
        # should still show the branched page.
        with app.test_request_context():
            from flask import session
            p = _make_participant(app)
            session['participantID'] = p.participantID

            pages, _ = AdminStatsService.fetch_progress()

        page_paths = [pg['path'] for pg in pages]
        assert 'questionnaire/branched' in page_paths, (
            "Progress table dropped a show_if-gated page; "
            f"got: {page_paths}"
        )


# ===========================================================================
# Tests for fetch_progress_summary
# ===========================================================================

class TestFetchProgressSummary:
    def test_fetch_progress_summary_groups_by_condition(self, bofs_app_with_questionnaires):
        """summary_groups contains one row per condition with correct counts."""
        app = bofs_app_with_questionnaires
        app.config['ABANDONED_MINUTES'] = 60

        _make_participant(app, condition=1)
        _make_participant(app, condition=1)
        _make_participant(app, condition=2)

        summary_groups, _ = AdminStatsService.fetch_progress_summary()

        conditions_in_groups = {row.condition for row in summary_groups}
        assert 1 in conditions_in_groups
        assert 2 in conditions_in_groups

        count_by_condition = {row.condition: row.count for row in summary_groups}
        assert count_by_condition[1] == 2
        assert count_by_condition[2] == 1

    def test_fetch_progress_summary_excludes_excluded(self, bofs_app_with_questionnaires):
        """Participants with excludeFromCount=True are filtered from both summary_groups and summary."""
        app = bofs_app_with_questionnaires
        app.config['ABANDONED_MINUTES'] = 60

        _make_participant(app, condition=1, excludeFromCount=False)
        _make_participant(app, condition=1, excludeFromCount=True)

        summary_groups, summary = AdminStatsService.fetch_progress_summary()

        # Only 1 participant should be counted
        assert summary.count == 1

        count_by_condition = {row.condition: row.count for row in summary_groups}
        assert count_by_condition.get(1, 0) == 1

    def test_fetch_progress_summary_summary_aggregates_overall(self, bofs_app_with_questionnaires):
        """summary.count is the total across all conditions, not per-condition."""
        app = bofs_app_with_questionnaires
        app.config['ABANDONED_MINUTES'] = 60

        _make_participant(app, condition=1)
        _make_participant(app, condition=1)
        _make_participant(app, condition=2)
        _make_participant(app, condition=2)
        _make_participant(app, condition=2)

        _, summary = AdminStatsService.fetch_progress_summary()

        assert summary.count == 5
