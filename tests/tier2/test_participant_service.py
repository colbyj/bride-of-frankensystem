"""Tier 2 tests for ParticipantService.

These tests require a Flask app context with an in-memory SQLite database.
They use the ``bofs_app`` fixture from conftest.py.
"""

import pytest
from flask import session

from BOFS.services.participant import ParticipantService


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
# TestParticipantService
# ===========================================================================

class TestParticipantService:

    def test_provide_consent_creates_participant_and_assigns_condition(self, bofs_app):
        """provide_consent(True) in debug mode creates a participant with condition==0."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True
        bofs_app.config["STATIC_COMPLETION_CODE"] = None
        bofs_app.config["GENERATE_COMPLETION_CODE"] = False

        # bofs_app is created with debug=True, so run_with_debugging is True.
        # In debug mode, condition is set to 0 rather than running the balancer.
        with bofs_app.test_request_context(
            "/consent",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            session.clear()
            p = ParticipantService.provide_consent(assign_condition=True)

        count = bofs_app.db.session.query(bofs_app.db.Participant).count()
        assert count == 1
        assert p.condition is not None  # condition is set (==0 in debug mode)
        assert p.participantID is not None

    def test_provide_consent_no_condition_sets_zero(self, bofs_app):
        """provide_consent(False) creates a participant with condition==0."""
        bofs_app.config["STATIC_COMPLETION_CODE"] = None
        bofs_app.config["GENERATE_COMPLETION_CODE"] = False

        with bofs_app.test_request_context(
            "/consent",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            session.clear()
            p = ParticipantService.provide_consent(assign_condition=False)

        assert p.condition == 0

    def test_assign_condition_organic_writes_session(self, bofs_app):
        """assign_condition_organic sets p.condition and writes session['condition']."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        p = _make_participant(bofs_app, condition=0)

        with bofs_app.test_request_context("/"):
            session.clear()
            ParticipantService.assign_condition_organic(p)
            assert p.condition is not None
            assert p.condition > 0
            assert session['condition'] == p.condition

    def test_assign_condition_explicit(self, bofs_app):
        """assign_condition_explicit sets p.condition to given value and writes session."""
        p = _make_participant(bofs_app, condition=0)

        with bofs_app.test_request_context("/"):
            session.clear()
            ParticipantService.assign_condition_explicit(p, condition_num=2)
            assert p.condition == 2
            assert session['condition'] == 2

    def test_clear_condition(self, bofs_app):
        """clear_condition sets p.condition to None."""
        p = _make_participant(bofs_app, condition=2)

        ParticipantService.clear_condition(p)

        refreshed = bofs_app.db.session.query(bofs_app.db.Participant).get(p.participantID)
        assert refreshed.condition is None

    def test_balancer_counts_delegates(self, bofs_app):
        """balancer_counts returns the same result as db.Participant.balancer_counts()."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=2)

        result = ParticipantService.balancer_counts()
        expected = bofs_app.db.Participant.balancer_counts()
        assert result == expected

    def test_compute_organic_condition_delegates(self, bofs_app):
        """compute_organic_condition returns same result as db.Participant.compute_organic_condition()."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
        ]
        bofs_app.config["COUNTS_INCLUDE_ABANDONED"] = True

        _make_participant(bofs_app, condition=1)

        result = ParticipantService.compute_organic_condition()
        expected = bofs_app.db.Participant.compute_organic_condition()
        assert result == expected

    def test_current_condition_reads_session(self, bofs_app):
        """current_condition() reads from session['condition']."""
        with bofs_app.test_request_context("/"):
            session['condition'] = 1
            assert ParticipantService.current_condition() == 1

    def test_current_condition_negative_one_maps_to_zero(self, bofs_app):
        """current_condition() maps session value -1 to 0."""
        with bofs_app.test_request_context("/"):
            session['condition'] = -1
            assert ParticipantService.current_condition() == 0

    def test_condition_count(self, bofs_app):
        """condition_count() returns len(CONDITIONS)."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": True},
            {"label": "B", "enabled": True},
            {"label": "C", "enabled": True},
        ]
        assert ParticipantService.condition_count() == 3

    def test_all_conditions_disabled_true(self, bofs_app):
        """all_conditions_disabled() returns True when all conditions have enabled=False."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": False},
            {"label": "B", "enabled": False},
        ]
        assert ParticipantService.all_conditions_disabled() is True

    def test_all_conditions_disabled_false_when_any_enabled(self, bofs_app):
        """all_conditions_disabled() returns False when at least one condition is enabled."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "A", "enabled": False},
            {"label": "B", "enabled": True},
        ]
        assert ParticipantService.all_conditions_disabled() is False

    def test_all_conditions_disabled_empty_returns_false(self, bofs_app):
        """all_conditions_disabled() returns False when CONDITIONS is empty."""
        bofs_app.config["CONDITIONS"] = []
        assert ParticipantService.all_conditions_disabled() is False

    def test_max_assigned_condition_db(self, bofs_app):
        """max_assigned_condition_db() returns the maximum condition value in the DB."""
        _make_participant(bofs_app, condition=1)
        _make_participant(bofs_app, condition=3)
        _make_participant(bofs_app, condition=2)

        result = ParticipantService.max_assigned_condition_db()
        assert result == 3

    def test_toggle_condition_enabled_flips(self, bofs_app):
        """toggle_condition_enabled flips True→False and False→True."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ]

        result = ParticipantService.toggle_condition_enabled(0)
        assert result is False
        assert bofs_app.config["CONDITIONS"][0]["enabled"] is False

        result = ParticipantService.toggle_condition_enabled(0)
        assert result is True
        assert bofs_app.config["CONDITIONS"][0]["enabled"] is True

    def test_toggle_condition_enabled_default_when_unset(self, bofs_app):
        """Missing 'enabled' key is treated as True; first toggle flips to False."""
        bofs_app.config["CONDITIONS"] = [{"label": "Control"}]

        result = ParticipantService.toggle_condition_enabled(0)
        assert result is False
        assert bofs_app.config["CONDITIONS"][0]["enabled"] is False

    def test_toggle_condition_enabled_returns_new_value(self, bofs_app):
        """Return value matches the post-toggle 'enabled' flag."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ]

        return_value = ParticipantService.toggle_condition_enabled(1)
        assert return_value == bofs_app.config["CONDITIONS"][1]["enabled"]

    def test_toggle_condition_enabled_invalid_index_raises(self, bofs_app):
        """Out-of-range index raises IndexError."""
        bofs_app.config["CONDITIONS"] = [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ]

        with pytest.raises(IndexError):
            ParticipantService.toggle_condition_enabled(2)

        with pytest.raises(IndexError):
            ParticipantService.toggle_condition_enabled(-999)
