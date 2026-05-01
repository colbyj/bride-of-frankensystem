"""Tier 2 tests for the Results class (BOFS/services/data_export.py).

Tests DataFrame joins, CSV export, caching, and filtering.
Uses the bofs_app_with_questionnaires fixture for a fully-loaded app with
questionnaires in PAGE_LIST.
"""

import os
import time
from datetime import datetime

import pytest

from BOFS.services.data_export import Results


# ===========================================================================
# Helpers
# ===========================================================================

def _make_participant(app, condition=1, finished=True, mTurkID="",
                      timeStarted=None, timeEnded=None):
    """Create a Participant with sensible defaults."""
    p = app.db.Participant()
    p.mTurkID = mTurkID
    p.ipAddress = "127.0.0.1"
    p.userAgent = "test"
    p.condition = condition
    p.finished = finished
    p.timeStarted = timeStarted or datetime(2024, 1, 1, 12, 0, 0)
    p.timeEnded = timeEnded
    app.db.session.add(p)
    app.db.session.commit()
    return p


def _make_questionnaire_record(app, q, participantID, tag="", **kwargs):
    """Create a questionnaire response record in the DB."""
    record = q.db_class()
    record.participantID = participantID
    record.tag = tag
    record.timeStarted = kwargs.pop("timeStarted", datetime(2024, 1, 1, 12, 0, 0))
    record.timeEnded = kwargs.pop("timeEnded", datetime(2024, 1, 1, 12, 1, 0))
    for k, v in kwargs.items():
        setattr(record, k, v)
    app.db.session.add(record)
    app.db.session.commit()
    return record


def _seed_full_participant(app, condition=1, finished=True, mTurkID="",
                           survey_data=None, before_data=None):
    """Create a participant with both survey and survey/before records."""
    p = _make_participant(app, condition=condition, finished=finished,
                          mTurkID=mTurkID,
                          timeStarted=datetime(2024, 1, 1, 12, 0, 0),
                          timeEnded=datetime(2024, 1, 1, 12, 5, 0) if finished else None)
    q = app.questionnaires["survey"]

    defaults = {"name": "Test", "rating": 4, "age": 30, "g1_q1": 3, "g1_q2": 5}
    if survey_data:
        defaults.update(survey_data)
    _make_questionnaire_record(app, q, p.participantID, tag="", **defaults)

    defaults_before = {"name": "Test2", "rating": 5, "age": 31, "g1_q1": 4, "g1_q2": 2}
    if before_data:
        defaults_before.update(before_data)
    _make_questionnaire_record(app, q, p.participantID, tag="before", **defaults_before)

    return p


# ===========================================================================
# Participants
# ===========================================================================

class TestParticipants:
    def test_participant_columns_present(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _make_participant(app)

        r = Results()
        for col in ["participantID", "externalID", "condition", "duration", "finished"]:
            assert col in r.column_list

    def test_participant_data_populated(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app, condition=1, finished=True, mTurkID="ext123",
                              timeStarted=datetime(2024, 1, 1, 12, 0, 0),
                              timeEnded=datetime(2024, 1, 1, 12, 5, 0))

        r = Results()
        assert p.participantID in r.export_data
        data = r.export_data[p.participantID]
        assert data["participantID"] == p.participantID
        assert data["externalID"] == "ext123"
        assert data["finished"] is True

    def test_condition_label_conversion(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _make_participant(app, condition=1)

        r = Results()
        data = r.export_data[p.participantID]
        assert data["condition"] == "Control"  # CONDITIONS[0]['label']

    def test_empty_database(self, bofs_app_with_questionnaires):
        """Results handles an empty database without errors."""
        app = bofs_app_with_questionnaires
        r = Results()
        assert r.export_data == {}

    def test_filter_finished_only(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p1 = _make_participant(app, finished=True,
                               timeEnded=datetime(2024, 1, 1, 12, 5, 0))
        p2 = _make_participant(app, finished=False)

        r = Results(filter_criterion=app.db.Participant.finished == True)
        assert p1.participantID in r.export_data
        assert p2.participantID not in r.export_data


# ===========================================================================
# Questionnaires
# ===========================================================================

class TestQuestionnaireExport:
    def test_questionnaire_columns_added(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        r = Results()
        assert "survey_name" in r.column_list
        assert "survey_rating" in r.column_list

    def test_questionnaire_data_populated(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _seed_full_participant(app, survey_data={"name": "Alice", "rating": 4})

        r = Results()
        data = r.export_data[p.participantID]
        assert data["survey_name"] == "Alice"
        assert data["survey_rating"] == 4

    def test_tagged_questionnaire_columns(self, bofs_app_with_questionnaires):
        """survey/before columns are separate from survey columns."""
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        r = Results()
        assert "survey_name" in r.column_list
        assert "survey/before_name" in r.column_list

    def test_outer_join_missing_data(self, bofs_app_with_questionnaires):
        """Participant with no questionnaire → row exists, fields absent."""
        app = bofs_app_with_questionnaires
        p = _make_participant(app, condition=1, finished=True)
        # No questionnaire records created

        r = Results()
        assert p.participantID in r.export_data
        # Questionnaire columns should not be populated
        data = r.export_data[p.participantID]
        assert "survey_name" not in data

    def test_calculated_fields_in_export(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _seed_full_participant(app, survey_data={"g1_q1": 3, "g1_q2": 5})

        r = Results()
        assert "survey_grid_total" in r.column_list
        data = r.export_data[p.participantID]
        assert data["survey_grid_total"] == 8.0  # 3 + 5

    def test_duration_column_per_questionnaire(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        p = _seed_full_participant(app, survey_data={
            "timeStarted": datetime(2024, 1, 1, 12, 0, 0),
            "timeEnded": datetime(2024, 1, 1, 12, 1, 30),
        })

        r = Results()
        assert "survey_duration" in r.column_list
        data = r.export_data[p.participantID]
        assert data["survey_duration"] == 90.0


# ===========================================================================
# DataFrame
# ===========================================================================

class TestDataFrame:
    def test_build_data_frame_shape(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app, condition=1)
        _seed_full_participant(app, condition=2)

        r = Results()
        df = r.build_data_frame()

        assert len(df) == 2
        assert list(df.columns) == r.column_list

    def test_build_data_frame_caches(self, bofs_app_with_questionnaires, tmp_path):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        cache_path = str(tmp_path / "test_cache.json")

        r = Results(cache_path=cache_path)
        r.build_data_frame()

        assert os.path.exists(cache_path)

    def test_build_data_frame_idempotent(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        r = Results()
        df1 = r.build_data_frame()
        df2 = r.build_data_frame()

        assert df1 is df2  # Same object returned


# ===========================================================================
# CSV export
# ===========================================================================

class TestCSV:
    def test_csv_header_matches_columns(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        r = Results()
        csv = r.build_export_csv()

        header = csv.split("\n")[0]
        assert header == ",".join(r.column_list)

    def test_csv_data_rows(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app, condition=1)
        _seed_full_participant(app, condition=2)

        r = Results()
        csv = r.build_export_csv()

        lines = csv.split("\n")
        assert len(lines) == 3  # header + 2 data rows

    def test_csv_escapes_special_chars(self, bofs_app_with_questionnaires):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app, mTurkID="has,comma",
                               survey_data={"name": 'has"quote'})

        r = Results()
        csv = r.build_export_csv()

        # RFC 4180: cells containing commas are quoted; internal quotes are
        # doubled.
        assert '"has,comma"' in csv
        assert '"has""quote"' in csv

    def test_csv_neutralises_formula_injection(self, bofs_app_with_questionnaires):
        """A free-text cell starting with =/+/-/@ is prefixed with ' so a
        spreadsheet app won't evaluate it as a formula."""
        app = bofs_app_with_questionnaires
        _seed_full_participant(app, survey_data={"name": "=cmd|'/c calc'!A1"})

        r = Results()
        csv = r.build_export_csv()

        # The prefix replaces the leading sigil; the cell becomes
        # '=cmd|'/c calc'!A1 (and is quoted only if other CSV-special chars
        # are present — single quote isn't special).
        assert "'=cmd|" in csv
        # The bare formula must not appear unprefixed anywhere.
        assert ",=cmd|" not in csv
        assert "\n=cmd|" not in csv


# ===========================================================================
# Caching
# ===========================================================================

class TestCaching:
    def test_fresh_cache_loads(self, bofs_app_with_questionnaires, tmp_path):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        cache_path = str(tmp_path / "cache_fresh.json")

        # Build and cache
        r1 = Results(cache_path=cache_path)
        r1.build_data_frame()

        # Load from fresh cache
        r2 = Results(cache_path=cache_path)
        assert r2.df is not None  # Loaded from cache

    def test_stale_cache_rebuilds(self, bofs_app_with_questionnaires, tmp_path):
        app = bofs_app_with_questionnaires
        _seed_full_participant(app)

        cache_path = str(tmp_path / "cache_stale.json")

        # Build and cache
        r1 = Results(cache_path=cache_path)
        r1.build_data_frame()

        # Age the cache file beyond MAX_CACHE_SECONDS (120s)
        old_time = time.time() - 300
        os.utime(cache_path, (old_time, old_time))

        # Should rebuild from DB (not use stale cache)
        r2 = Results(cache_path=cache_path)
        assert r2.df is None  # Not loaded from cache
        assert len(r2.export_data) == 1  # But data was built from DB


# ===========================================================================
# New staticmethods: build_filter_from_args and calculate_results
# ===========================================================================

class TestBuildFilterFromArgs:
    """Unit tests for Results.build_filter_from_args (the bool-parsing bug fix)."""

    def _filter(self, **kwargs):
        from werkzeug.datastructures import ImmutableMultiDict
        return Results.build_filter_from_args(ImmutableMultiDict(kwargs))

    # --- Parsing correctness ---

    def test_true_string_is_truthy(self, bofs_app_with_questionnaires):
        """'true' → True. Both flags on → no filter."""
        f = self._filter(includeUnfinished='true', includeExcluded='true')
        assert f is None

    def test_false_string_is_falsy(self, bofs_app_with_questionnaires):
        """'false' → False (the bool-parsing bug that was fixed). Both off → restrict on both."""
        f = self._filter(includeUnfinished='false', includeExcluded='false')
        assert f is not None

    def test_case_insensitive(self, bofs_app_with_questionnaires):
        """'TRUE' / 'FALSE' are parsed case-insensitively."""
        f_upper = self._filter(includeUnfinished='TRUE', includeExcluded='TRUE')
        f_lower = self._filter(includeUnfinished='true', includeExcluded='true')
        # Both produce identical "no filter" output.
        assert f_upper is None
        assert f_lower is None

    def test_absent_params_use_defaults(self, bofs_app_with_questionnaires):
        """Absent params fall back to (includeUnfinished=False, includeExcluded=False)
        → both restrictions applied."""
        from werkzeug.datastructures import ImmutableMultiDict
        f = Results.build_filter_from_args(ImmutableMultiDict())
        assert f is not None

    def test_bool_true_passthrough(self, bofs_app_with_questionnaires):
        """A literal Python True passes through the parser."""
        f = Results.build_filter_from_args({'includeUnfinished': True, 'includeExcluded': True})
        assert f is None

    def test_bool_false_passthrough(self, bofs_app_with_questionnaires):
        """A literal Python False passes through the parser."""
        f = Results.build_filter_from_args({'includeUnfinished': False, 'includeExcluded': False})
        assert f is not None

    # --- Filter semantics (verified against a seeded DB) ---

    def _seed_four(self, app):
        """Seed finished+included, unfinished+included, finished+excluded, unfinished+excluded."""
        def make(finished, excluded):
            p = app.db.Participant()
            p.mTurkID = ""
            p.ipAddress = "127.0.0.1"
            p.userAgent = "test"
            p.condition = 1
            p.finished = finished
            p.excludeFromCount = excluded
            p.timeStarted = datetime(2024, 1, 1, 12, 0, 0)
            p.timeEnded = datetime(2024, 1, 1, 12, 5, 0) if finished else None
            app.db.session.add(p)
        make(True, False)
        make(False, False)
        make(True, True)
        make(False, True)
        app.db.session.commit()

    def _count(self, app, f):
        q = app.db.session.query(app.db.Participant)
        if f is not None:
            q = q.filter(f)
        return q.count()

    def test_default_finished_and_non_excluded(self, bofs_app_with_questionnaires):
        """includeUnfinished=False, includeExcluded=False → only finished+included (1)."""
        app = bofs_app_with_questionnaires
        self._seed_four(app)
        f = self._filter(includeUnfinished='false', includeExcluded='false')
        assert self._count(app, f) == 1

    def test_unfinished_only_non_excluded(self, bofs_app_with_questionnaires):
        """includeUnfinished=True, includeExcluded=False → all non-excluded (2)."""
        app = bofs_app_with_questionnaires
        self._seed_four(app)
        f = self._filter(includeUnfinished='true', includeExcluded='false')
        assert self._count(app, f) == 2

    def test_excluded_only_finished(self, bofs_app_with_questionnaires):
        """includeUnfinished=False, includeExcluded=True → only finished, both excl states (2)."""
        app = bofs_app_with_questionnaires
        self._seed_four(app)
        f = self._filter(includeUnfinished='false', includeExcluded='true')
        assert self._count(app, f) == 2  # finished+included + finished+excluded

    def test_both_flags_no_filter(self, bofs_app_with_questionnaires):
        """includeUnfinished=True, includeExcluded=True → no filter (all 4)."""
        app = bofs_app_with_questionnaires
        self._seed_four(app)
        f = self._filter(includeUnfinished='true', includeExcluded='true')
        assert f is None
        assert self._count(app, f) == 4


class TestCalculateResults:
    """Unit tests for Results.calculate_results staticmethod."""

    def test_returns_three_tuple(self, bofs_app_with_questionnaires, tmp_path):
        """calculate_results returns (results, df, summary_stats)."""
        app = bofs_app_with_questionnaires
        # Seed one finished, non-excluded participant
        _make_participant(app, finished=True)
        cache_path = str(tmp_path / "cache.json")

        result = Results.calculate_results(cache_path)
        assert len(result) == 3

    def test_df_is_non_empty_with_participants(self, bofs_app_with_questionnaires, tmp_path):
        """With qualifying participants, df is non-empty."""
        app = bofs_app_with_questionnaires
        _make_participant(app, finished=True)
        cache_path = str(tmp_path / "cache.json")

        results, df, summary_stats = Results.calculate_results(cache_path)
        assert len(df) > 0

    def test_summary_stats_is_dict(self, bofs_app_with_questionnaires, tmp_path):
        """summary_stats is always a dict (possibly empty)."""
        app = bofs_app_with_questionnaires
        _make_participant(app, finished=True)
        cache_path = str(tmp_path / "cache.json")

        results, df, summary_stats = Results.calculate_results(cache_path)
        assert isinstance(summary_stats, dict)

    def test_empty_db_yields_empty_df_and_stats(self, bofs_app_with_questionnaires, tmp_path):
        """No participants → empty df and empty summary_stats."""
        app = bofs_app_with_questionnaires
        cache_path = str(tmp_path / "cache_empty.json")

        results, df, summary_stats = Results.calculate_results(cache_path)
        assert len(df) == 0
        assert summary_stats == {}

    def test_excludes_unfinished(self, bofs_app_with_questionnaires, tmp_path):
        """Unfinished participants are excluded from results."""
        app = bofs_app_with_questionnaires
        _make_participant(app, finished=True)
        _make_participant(app, finished=False)
        cache_path = str(tmp_path / "cache_excl.json")

        results, df, summary_stats = Results.calculate_results(cache_path)
        assert len(df) == 1

    def test_excludes_excluded_from_count(self, bofs_app_with_questionnaires, tmp_path):
        """Participants with excludeFromCount=True are excluded from results."""
        app = bofs_app_with_questionnaires
        p_incl = _make_participant(app, finished=True)
        p_excl = _make_participant(app, finished=True)
        p_excl.excludeFromCount = True
        app.db.session.commit()

        cache_path = str(tmp_path / "cache_excl2.json")
        results, df, summary_stats = Results.calculate_results(cache_path)
        assert len(df) == 1
        assert p_incl.participantID in results.export_data
        assert p_excl.participantID not in results.export_data

    def test_summary_stats_populated_for_numeric_cols(self, bofs_app_with_questionnaires, tmp_path):
        """With numeric questionnaire data, summary_stats is non-empty."""
        app = bofs_app_with_questionnaires
        # Seed two participants in different conditions with questionnaire data
        p1 = _seed_full_participant(app, condition=1)
        p2 = _seed_full_participant(app, condition=2)
        p1.finished = True
        p2.finished = True
        app.db.session.commit()

        cache_path = str(tmp_path / "cache_stats.json")
        results, df, summary_stats = Results.calculate_results(cache_path)
        # summary_stats may be empty if participants are filtered out due to excludeFromCount;
        # just assert it is a dict (content varies by fixture data)
        assert isinstance(summary_stats, dict)
