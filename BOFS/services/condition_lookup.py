"""Look up a participant's condition by external ID from a CSV file or a prior
study's database.

Used to support longitudinal studies (day N must reuse the condition assigned
on day 0) and pre-assigned-by-list studies. See the longitudinal example in
the docs for context.

Two sources are supported. Both are configured per-project in the TOML config:

  CONDITIONS_FROM_CSV = 'conditions.csv'      # path relative to working dir
  CONDITIONS_FROM_DB  = 'sqlite:///day0.db'   # any SQLAlchemy URI

Either can be set on its own; if both are set, the CSV is consulted first.

When at least one source is configured, an external ID that is *not* found
raises ConditionLookupMiss. We never silently fall back to the balancer in
that situation — a typo in the CSV or an unauthorized participant should
surface clearly. Projects that genuinely want mixed pre-assigned-plus-balanced
behavior can call lookup() from their own blueprint and call the balancer on
None.
"""

import csv
import os
from typing import Mapping, Optional

from flask import current_app
from sqlalchemy import create_engine, text


_EXTENSION_KEY = 'bofs_condition_lookup'


class ConditionLookupMiss(Exception):
    """An external ID was looked up against a configured source but not found.

    Raised from Participant.assign_condition when CONDITIONS_FROM_CSV or
    CONDITIONS_FROM_DB is set but the participant's externalID isn't present.
    """

    def __init__(self, external_id: str):
        super().__init__(f"External ID {external_id!r} not found in any "
                         f"configured condition lookup source.")
        self.external_id = external_id


class ConditionLookupConfigError(Exception):
    """Startup validation of CONDITIONS_FROM_* failed."""


class ConditionLookupService:
    """Stateless lookup helpers. State lives on app.extensions[_EXTENSION_KEY]."""

    # ---------------- Startup ----------------

    @staticmethod
    def init_app(app) -> None:
        """Validate configured sources and cache parsed/opened state on the app.

        Called from create_app once config defaults are in place. Raises
        ConditionLookupConfigError on any validation failure.
        """
        state = {
            'csv_map': None, 'csv_path': None,
            'db_engine': None, 'db_uri': None,
            # Column name in the prior DB's `participant` table holding the
            # external ID. New BOFS DBs use `external_id`; pre-rename DBs use
            # `mTurkID`. Detected at startup so a single string substitution
            # serves every later query.
            'db_external_id_col': None,
        }

        csv_path = app.config.get('CONDITIONS_FROM_CSV')
        if csv_path:
            state['csv_map'] = ConditionLookupService._load_csv(csv_path, app.config['CONDITIONS'])
            state['csv_path'] = csv_path

        db_uri = app.config.get('CONDITIONS_FROM_DB')
        if db_uri:
            engine, detected_col = ConditionLookupService._open_db(db_uri)
            state['db_engine'] = engine
            state['db_uri'] = db_uri
            state['db_external_id_col'] = detected_col

        app.extensions[_EXTENSION_KEY] = state

    @staticmethod
    def _load_csv(csv_path: str, conditions: list) -> dict:
        """Parse a two-column CSV (header + rows of external_id, condition).

        Validates: file exists, header present, rows are well-formed, condition
        values are integers within 1..len(CONDITIONS).
        """
        if not os.path.isfile(csv_path):
            raise ConditionLookupConfigError(
                f"CONDITIONS_FROM_CSV={csv_path!r} does not exist (looked relative "
                f"to {os.getcwd()!r})."
            )

        num_conditions = len(conditions)
        result: dict = {}

        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                raise ConditionLookupConfigError(
                    f"CONDITIONS_FROM_CSV={csv_path!r} is empty (expected header "
                    f"row 'id,condition')."
                )

            if len(header) < 2:
                raise ConditionLookupConfigError(
                    f"CONDITIONS_FROM_CSV={csv_path!r} header must have at least "
                    f"two columns (id, condition); got {header!r}."
                )

            # +2 because line 1 is the header and enumerate starts at 0.
            for line_no, row in enumerate(reader, start=2):
                if not row or all(cell.strip() == '' for cell in row):
                    continue
                if len(row) < 2:
                    raise ConditionLookupConfigError(
                        f"CONDITIONS_FROM_CSV={csv_path!r} line {line_no} has "
                        f"fewer than 2 columns: {row!r}."
                    )
                external_id = row[0].strip()
                raw_condition = row[1].strip()

                if not external_id:
                    raise ConditionLookupConfigError(
                        f"CONDITIONS_FROM_CSV={csv_path!r} line {line_no} has an "
                        f"empty id."
                    )

                try:
                    condition_num = int(raw_condition)
                except ValueError:
                    raise ConditionLookupConfigError(
                        f"CONDITIONS_FROM_CSV={csv_path!r} line {line_no}: "
                        f"condition value {raw_condition!r} is not an integer."
                    )

                if num_conditions > 0 and not (1 <= condition_num <= num_conditions):
                    raise ConditionLookupConfigError(
                        f"CONDITIONS_FROM_CSV={csv_path!r} line {line_no}: "
                        f"condition {condition_num} is out of range "
                        f"(must be 1..{num_conditions})."
                    )

                if external_id in result and result[external_id] != condition_num:
                    raise ConditionLookupConfigError(
                        f"CONDITIONS_FROM_CSV={csv_path!r} line {line_no}: id "
                        f"{external_id!r} appears twice with conflicting "
                        f"conditions ({result[external_id]} and {condition_num})."
                    )

                result[external_id] = condition_num

        return result

    @staticmethod
    def _open_db(db_uri: str):
        """Create a read-only-intent SQLAlchemy engine for the prior-study DB
        and verify it has a usable participant table.

        Returns ``(engine, external_id_column_name)``. The column name is
        whichever of ``external_id`` (new BOFS schema) or ``mTurkID``
        (pre-rename BOFS schema) is present. When both exist (an
        upgrade-rollback edge case), ``external_id`` wins.
        """
        try:
            engine = create_engine(db_uri)
        except Exception as exc:
            raise ConditionLookupConfigError(
                f"CONDITIONS_FROM_DB={db_uri!r} is not a valid SQLAlchemy URI: {exc}"
            )

        # Try the new column name first, then fall back to the legacy name.
        # The LIMIT 0 SELECT is dialect-agnostic (works on SQLite, Postgres,
        # MySQL, etc.) and avoids depending on SQLite-only PRAGMAs.
        detected_col = None
        last_exc = None
        for candidate in ('external_id', 'mTurkID'):
            try:
                with engine.connect() as conn:
                    conn.execute(text(
                        f"SELECT {candidate}, condition FROM participant LIMIT 0"
                    ))
                detected_col = candidate
                break
            except Exception as exc:
                last_exc = exc

        if detected_col is None:
            raise ConditionLookupConfigError(
                f"CONDITIONS_FROM_DB={db_uri!r} could not be opened or its "
                f"'participant' table is missing the required external-ID "
                f"column (looked for 'external_id' or 'mTurkID') and "
                f"'condition' column: {last_exc}"
            )

        return engine, detected_col

    # ---------------- Runtime ----------------

    @staticmethod
    def _state() -> Optional[dict]:
        return current_app.extensions.get(_EXTENSION_KEY)

    @staticmethod
    def is_configured() -> bool:
        """True iff CONDITIONS_FROM_CSV or CONDITIONS_FROM_DB is set."""
        state = ConditionLookupService._state()
        if not state:
            return False
        return state['csv_map'] is not None or state['db_engine'] is not None

    @staticmethod
    def lookup(external_id: str) -> Optional[int]:
        """Try CSV (if configured) then DB. Returns the 1-based condition int
        if found, or None if not present in any configured source.

        Returns None when no source is configured at all — callers that want
        to error in that case should check is_configured() first.
        """
        if not external_id:
            return None

        state = ConditionLookupService._state()
        if not state:
            return None

        external_id = external_id.strip()

        if state['csv_map'] is not None:
            hit = state['csv_map'].get(external_id)
            if hit is not None:
                return hit

        if state['db_engine'] is not None:
            row = ConditionLookupService._query_db(
                state['db_engine'], external_id, state['db_external_id_col'],
            )
            if row is not None:
                return row['condition']

        return None

    @staticmethod
    def find_prior_participant(external_id: str) -> Optional[Mapping]:
        """Return the prior-study participant row matching *external_id*, or
        None. Intended as an escape hatch for projects that need more than
        the condition (e.g., to read a prior questionnaire response for a
        stratified balancer).

        Returns a read-only mapping (column name → value). The exact set of
        columns depends on the prior DB's schema.
        """
        state = ConditionLookupService._state()
        if not state or state['db_engine'] is None or not external_id:
            return None
        return ConditionLookupService._query_db(
            state['db_engine'], external_id.strip(), state['db_external_id_col'],
        )

    @staticmethod
    def open_prior_db():
        """SQLAlchemy Engine for CONDITIONS_FROM_DB, or None. Cached on the app.

        Custom blueprints that need to run their own queries against the prior
        study's DB can borrow this engine instead of opening their own.
        """
        state = ConditionLookupService._state()
        if not state:
            return None
        return state['db_engine']

    @staticmethod
    def _query_db(engine, external_id: str, id_col: str) -> Optional[dict]:
        """Look up a participant row in the prior DB.

        ``id_col`` is the participant-table column holding the external ID,
        as detected at startup (``external_id`` for new BOFS DBs,
        ``mTurkID`` for pre-rename ones).

        Prefers a finished attempt over an unfinished one, and the most
        recent attempt within those. Skips rows where condition is NULL or 0,
        which represent consent-only abandons.
        """
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT * FROM participant "
                    f"WHERE {id_col} = :external_id "
                    f"  AND condition IS NOT NULL AND condition != 0 "
                    f"ORDER BY finished DESC, participantID DESC "
                    f"LIMIT 1"
                ),
                {'external_id': external_id},
            )
            row = result.mappings().first()
            return dict(row) if row is not None else None
