"""Data export service for BOFS.

The Results class and associated helpers for building participant data exports,
DataFrames, and summary statistics.
"""

from sqlalchemy.orm import Query
from BOFS.globals import db, questionnaires, page_list
import sqlalchemy
from BOFS.admin.util import csv_string, questionnaire_name_and_tag, condition_num_to_label
from flask import current_app
# NOTE: pandas is imported lazily inside the few methods that need it.
import os
from datetime import datetime, timezone
from typing import Union

from BOFS.util import utcnow_naive
from BOFS.validation import is_sql_expression_safe

MAX_CACHE_SECONDS = 60 * 2


def _safe_sql_text(expr: str, source: str):
    """Wrap a researcher-authored expression in db.text after validating it.

    Raises ValueError if the expression isn't allow-list-clean. Validation
    also runs at table load time (see validation.validate_table); this is
    defence in depth so a hand-built export definition or a config path that
    bypasses validation can't reach raw db.text().
    """
    ok, why = is_sql_expression_safe(expr)
    if not ok:
        raise ValueError(f"Unsafe SQL expression in {source}: {why}")
    return db.text(expr)


def _safe_literal_column(expr: str, source: str):
    ok, why = is_sql_expression_safe(expr)
    if not ok:
        raise ValueError(f"Unsafe SQL expression in {source}: {why}")
    return db.literal_column(expr)


class Results(object):
    def __init__(self, filter_criterion=None, cache_path: Union[str, None] = None):
        self.cache_path = cache_path
        use_cache = False

        if cache_path is not None:
            if os.path.exists(cache_path):
                modified_time = datetime.fromtimestamp(os.path.getmtime(cache_path), tz=timezone.utc).replace(tzinfo=None)
                if (utcnow_naive() - modified_time).total_seconds() < MAX_CACHE_SECONDS:
                    use_cache = True

        self.df = None
        self.column_list: list[str] = []
        # Maps bind_key (``None`` for the default bind) to the columns owned
        # by that bind, so :meth:`build_export_csv_for_bind` can emit a CSV
        # that contains only its own questionnaires/tables. Every non-default
        # bind's CSV is joinable on ``participantID``.
        self.column_list_by_bind: dict = {None: []}
        # Maps non-default bind_key to the set of participantIDs that have
        # at least one row on that bind. ``build_export_csv_for_bind`` reads
        # this to decide which participants to include in each per-bind CSV;
        # a participant who submitted nothing on the bind is omitted rather
        # than written as a row of empty cells. Default-bind participants
        # are not tracked here — they all appear in the default CSV by
        # construction (every participantID comes from the Participant
        # table on the default bind).
        self._bind_pids: dict = {}
        self.export_data: Union[dict[str, dict], dict] = {}
        """Keys are participant IDs, value is a dictionary of all columns."""
        self.query_participants: Query
        self.query_filter_criterion = filter_criterion

        if use_cache:
            self.load_data_frame()
        else:
            self.handle_participants_table()
            self.handle_questionnaires()
            self.handle_custom_exports()

    def handle_participants_table(self) -> None:
        """
        Add participant columns to column_list and their data to export_data.
        :param column_list: A list of strings that will be the columns in the CSV export.
        :param export_data: Gets updated with data for the participants
        :return: A SQLAlchemy query.
        """
        self.query_participants = db.session.query(db.Participant)

        if self.query_filter_criterion is not None:
            self.query_participants = self.query_participants.filter(self.query_filter_criterion)

        participant_cols = [
            "participantID",
            "externalID",
            "source",
            "condition",
            "duration",
            "finished",
            "end_reason",
        ]
        self.column_list.extend(participant_cols)
        self.column_list_by_bind[None].extend(participant_cols)

        query_result = self.query_participants.all()

        for row in query_result:
            self.export_data[row.participantID] = {
                'participantID': row.participantID,
                'externalID': row.externalID,
                'source': row.source or "",
                'condition': condition_num_to_label(row.condition),
                'duration': row.duration,
                'finished': row.finished,
                'end_reason': row.end_reason or "",
            }

    def handle_questionnaires(self) -> None:
        list_of_questionnaires = page_list.get_questionnaire_list(include_tags=True)

        # Group entries by bind so we can use the existing JOIN strategy for
        # the default bind (preserves byte-identical column ordering) and
        # query each non-default bind on its own engine (cross-bind JOINs
        # aren't possible — different engines, possibly different dialects).
        by_bind: dict = {}
        for entry in list_of_questionnaires:
            qname, _ = questionnaire_name_and_tag(entry)
            q = questionnaires[qname]
            by_bind.setdefault(getattr(q, 'bind_key', None), []).append(entry)

        # Default-bind group: today's JOIN against the Participant query.
        default_entries = by_bind.pop(None, [])
        if default_entries:
            self._handle_default_bind_questionnaires(default_entries)

        # Non-default binds: separate query per bind.
        for bind_key, entries in by_bind.items():
            self._handle_cross_bind_questionnaires(bind_key, entries)

    def _handle_default_bind_questionnaires(self, entries: list) -> None:
        query_questionnaires = self.query_participants
        q_columns = {}
        q_calculated_columns = {}

        for entry in entries:
            q_columns[entry] = []
            q_calculated_columns[entry] = []
            questionnaire_name, questionnaire_tag = questionnaire_name_and_tag(entry)
            questionnaire = questionnaires[questionnaire_name]

            questionnaire_db_class = db.aliased(questionnaire.db_class, name=entry)
            join_condition = db.and_(
                questionnaire_db_class.participantID == db.Participant.participantID,
                questionnaire_db_class.tag == questionnaire_tag,
            )

            query_questionnaires = query_questionnaires.outerjoin(
                questionnaire_db_class, join_condition
            ).add_entity(questionnaire_db_class)

            for column in questionnaire.fetch_fields():
                col_name = entry + "_" + column.id
                self.column_list.append(col_name)
                self.column_list_by_bind[None].append(col_name)
                q_columns[entry].append(column.id)

            for column in questionnaire.get_calculated_fields():
                col_name = entry + "_" + column
                self.column_list.append(col_name)
                self.column_list_by_bind[None].append(col_name)
                q_calculated_columns[entry].append(column)

            duration_col = entry + "_duration"
            self.column_list.append(duration_col)
            self.column_list_by_bind[None].append(duration_col)

        query_result = query_questionnaires.all()

        for row in query_result:
            for entry in entries:
                questionnaire_data = getattr(row, entry)
                if not questionnaire_data:
                    continue
                pid = row.Participant.participantID
                for col in q_columns[entry]:
                    self.export_data[pid][entry + "_" + col] = getattr(questionnaire_data, col)
                for col in q_calculated_columns[entry]:
                    self.export_data[pid][entry + "_" + col] = getattr(questionnaire_data, col)()
                self.export_data[pid][entry + "_duration"] = questionnaire_data.duration()

    def _handle_cross_bind_questionnaires(self, bind_key: str, entries: list) -> None:
        """Pull rows for questionnaires on a non-default bind.

        Cross-bind tables have no FK to ``Participant`` and live on a
        different engine, so we can't JOIN. Query each (questionnaire, tag)
        directly, filtering by the ``participantID`` integer column.
        """
        known_pids = list(self.export_data.keys())
        bind_columns = self.column_list_by_bind.setdefault(bind_key, [])
        bind_pids = self._bind_pids.setdefault(bind_key, set())
        # Every per-bind CSV leads with participantID + externalID so it's
        # joinable to the default-bind CSV (and recognisable on its own when
        # MTurk/Prolific IDs are in use).
        for key_col in ("participantID", "externalID"):
            if key_col not in bind_columns:
                bind_columns.append(key_col)

        for entry in entries:
            questionnaire_name, questionnaire_tag = questionnaire_name_and_tag(entry)
            questionnaire = questionnaires[questionnaire_name]
            q_class = questionnaire.db_class

            field_ids = [f.id for f in questionnaire.fetch_fields()]
            calc_field_ids = list(questionnaire.get_calculated_fields() or [])

            for col_id in field_ids:
                col_name = entry + "_" + col_id
                self.column_list.append(col_name)
                bind_columns.append(col_name)
            for col_id in calc_field_ids:
                col_name = entry + "_" + col_id
                self.column_list.append(col_name)
                bind_columns.append(col_name)
            duration_col = entry + "_duration"
            self.column_list.append(duration_col)
            bind_columns.append(duration_col)

            if not known_pids:
                continue

            rows = db.session.query(q_class).filter(
                q_class.tag == questionnaire_tag,
                q_class.participantID.in_(known_pids),
            ).all()

            for row in rows:
                pid = row.participantID
                if pid not in self.export_data:
                    continue
                # Mirror the participantID into the row dict so it appears
                # in the per-bind CSV even when the participant submitted
                # only this bind's questionnaire.
                self.export_data[pid].setdefault("participantID", pid)
                bind_pids.add(pid)
                for col_id in field_ids:
                    self.export_data[pid][entry + "_" + col_id] = getattr(row, col_id)
                for col_id in calc_field_ids:
                    self.export_data[pid][entry + "_" + col_id] = getattr(row, col_id)()
                self.export_data[pid][entry + "_duration"] = row.duration()

    def handle_custom_exports(self) -> None:
        # Repeated measures in other tables...
        custom_exports = []

        for export in current_app.config['EXPORT']:
            levels, fields, base_query = self.create_export_base_query(export)
            # Bind: read from the table class. JSONTable-defined tables set
            # ``__bind_key__`` when ``database`` is configured; hand-written
            # SQLAlchemy models in researcher blueprints either set it
            # explicitly or default to None (the default bind).
            table_class = getattr(db, export['table'])
            bind_key = getattr(table_class, '__bind_key__', None)
            custom_exports.append({
                'options': export, 'fields': fields, 'base_query': base_query,
                'levels': levels, 'bind_key': bind_key,
            })

        # For custom exports, add columns based on levels determined by prior query
        for export in custom_exports:
            bind_columns = self.column_list_by_bind.setdefault(export['bind_key'], [])
            # Cross-bind CSVs need participantID + externalID as join keys;
            # default-bind already added the full participant column set via
            # handle_participants_table.
            if export['bind_key'] is not None:
                for key_col in ("participantID", "externalID"):
                    if key_col not in bind_columns:
                        bind_columns.append(key_col)

            if export['levels']:
                for level in export['levels']:
                    for field in export['options']['fields']:
                        column_header = str.format("{}", field)
                        for level_name in level:
                            column_header += str.format("_{}", str(level_name).replace(" ", "_"))
                        self.column_list.append(column_header)
                        bind_columns.append(column_header)
            else:
                for field in export['options']['fields']:
                    col_name = str.format(u"{}", field)
                    self.column_list.append(col_name)
                    bind_columns.append(col_name)

        query_result = self.query_participants.all()

        # Now we get the actual data
        for row in query_result:
            participant_id = row.participantID

            for export in custom_exports:
                query = export['base_query']
                query = query.filter(db.literal_column('participantID') == row.participantID)
                custom_export_data = query.all()  # Running separate queries will get the job done, but be kind of slow with many participants...

                export_row_index = 0
                for custom_export_row in custom_export_data:
                    # Cross-bind rows: mirror participantID into the row dict
                    # so the per-bind CSV can use it as the join key, and
                    # record that this participant has data on this bind.
                    if export['bind_key'] is not None:
                        self.export_data[participant_id].setdefault("participantID", participant_id)
                        self._bind_pids.setdefault(
                            export['bind_key'], set()
                        ).add(participant_id)
                    for field in export['fields']:
                        export_column_name = field
                        if export['levels']:
                            export_column_name = field + "_" + str(export['levels'][export_row_index][0])

                        self.export_data[participant_id][export_column_name] = getattr(custom_export_row, field)

                    export_row_index += 1

    def create_export_base_query(self, export_definition: dict) -> tuple[list, list, "Query"]:
        """
        Builds the base query for exporting values in blueprint-defined tables.
        To be used for each entry in the config's EXPORT
        :param export_definition:
        :return: levels, fields, baseQuery
        """
        table = getattr(db, export_definition['table'])

        levels = None
        fields = []
        filter = None
        groupBy = None
        orderBy = None
        having = None

        export_label = (
            f"EXPORT[table={export_definition.get('table')!r}]"
        )

        if 'filter' in export_definition and export_definition['filter'] != '':
            filter = _safe_sql_text(
                export_definition['filter'], f"{export_label} filter"
            )

        if 'order_by' in export_definition and export_definition['order_by'] != '':
            orderBy = getattr(table, export_definition['order_by'])

        # Determine how many columns to add to the export. If group_by is not used, then it's just one column
        if 'group_by' in export_definition and export_definition['group_by'] != '':
            if 'having' in export_definition and export_definition['having'] != '':  # Having can only work if group_by is used.
                having = _safe_sql_text(
                    export_definition['having'], f"{export_label} having"
                )

            levelsQ = db.session.query()

            if isinstance(export_definition['group_by'], list):
                groupBy = []
                for gb in export_definition['group_by']:
                    groupBy.append(getattr(table, gb))
                    levelsQ = levelsQ.add_columns(getattr(table, gb))
                    levelsQ = levelsQ.group_by(getattr(table, gb))
            else:
                groupBy = getattr(table, export_definition['group_by'])
                levelsQ = levelsQ.add_columns(groupBy)
                levelsQ = levelsQ.group_by(groupBy)

            if orderBy:
                levelsQ = levelsQ.order_by(orderBy)

            if filter is not None:
                levels = levelsQ.filter(filter).all()
            else:
                levels = levelsQ.all()

        # pk = db.inspect(table).primary_key[0]
        baseQuery = db.session.query(table)

        if groupBy:
            if isinstance(groupBy, list):
                for gb in groupBy:
                    baseQuery = baseQuery.group_by(getattr(table, 'participantID'), gb)
            else:
                baseQuery = baseQuery.group_by(getattr(table, 'participantID'), groupBy)

            if having is not None:
                baseQuery = baseQuery.having(having)
        else:
            baseQuery = baseQuery.group_by(getattr(table, 'participantID'))

        if orderBy:
            baseQuery = baseQuery.order_by(orderBy)

        if filter is not None:
            baseQuery = baseQuery.filter(filter)

        # Add the fields to the basequery
        for field in export_definition['fields']:
            if hasattr(table, field) and callable(getattr(table, field)):
                continue  # We can't include this python property as part of the query
            fields.append(field)
            baseQuery = baseQuery.add_columns(
                _safe_literal_column(
                    export_definition['fields'][field],
                    f"{export_label} fields[{field!r}]",
                ).label(field)
            )

        return levels, fields, baseQuery

    def load_data_frame(self):
        import pandas as pd
        df = pd.read_json(self.cache_path)
        self.handle_participants_table()

        # Compare participant identities, not just counts. A count check
        # alone misses the case where one participant was added since the
        # cache was written and another was excluded — the IDs differ but
        # the totals match, then the per-ID lookup below raises IndexError
        # on the missing-from-cache row.
        has_pid_column = "participantID" in df.columns
        cached_ids = set(df["participantID"].tolist()) if has_pid_column else set()
        live_ids = set(self.export_data.keys())

        # A cache written when there were zero participants serializes to an
        # empty frame with no columns; treat that as a miss so the column
        # access below can't KeyError when live participants are also absent.
        if not has_pid_column or cached_ids != live_ids:
            self.handle_questionnaires()
            self.handle_custom_exports()
            return

        self.df = df
        self.column_list = self.df.columns.values.tolist()

        # Build the per-participant dict in a single pass. The previous version
        # re-filtered the whole frame once per cell (a boolean mask per cell,
        # O(rows^2 * cols)), which was both slow and memory-heavy on large
        # studies. to_dict("records") is one pass; key by participantID.
        for record in df.to_dict(orient="records"):
            self.export_data[record["participantID"]] = record

    def build_data_frame(self) -> "pd.DataFrame":
        import pandas as pd
        if self.df is not None:
            return self.df

        data = []
        for key in self.export_data:
            data.append(self.export_data[key])

        self.df = pd.DataFrame(data)

        if self.cache_path is not None:
            self.df.to_json(self.cache_path)

        return self.df

    def build_data_frame_for_bind(self, bind_key) -> "pd.DataFrame":
        """Return a DataFrame containing only the columns and rows for
        *bind_key*. Used by the admin export preview when binds are
        configured so the operator sees one DB at a time, not a merged
        cross-bind view that masks the privacy separation.
        """
        import pandas as pd
        columns = self.column_list_by_bind.get(bind_key, [])
        if bind_key is None:
            pids = list(self.export_data.keys())
        else:
            pid_filter = self._bind_pids.get(bind_key, set())
            pids = [pid for pid in self.export_data if pid in pid_filter]
        data = [
            {col: self.export_data[pid].get(col, "") for col in columns}
            for pid in pids
        ]
        return pd.DataFrame(data, columns=columns)

    def build_export_csv(self) -> str:
        rows = [list(self.column_list)]
        for row in self.export_data.values():
            rows.append([row.get(column, "") for column in self.column_list])
        # csv_string ends with a trailing newline; existing callers expected
        # no trailing newline, so strip it.
        return csv_string(rows).rstrip("\n")

    def build_export_csv_for_bind(self, bind_key) -> str:
        """Return a CSV containing only columns owned by *bind_key*.

        Pass ``None`` for the default bind (participant columns plus
        default-bind questionnaires/tables). Every non-default bind's CSV
        leads with ``participantID`` so the operator can rejoin to the
        default-bind CSV when they need to.

        Participants who didn't submit anything on a non-default bind are
        omitted from that bind's CSV — included only when at least one row
        actually exists for them on that engine, as recorded in
        ``self._bind_pids`` by the cross-bind handlers.

        Returns an empty string when the bind has no columns (e.g. a
        configured-but-unused bind).

        .. warning:: Do not call after :meth:`load_data_frame` populates
            ``Results`` from cache. The cache path only restores
            ``column_list`` / ``export_data``, not ``column_list_by_bind``
            or ``_bind_pids``, so a per-bind CSV built from a cached
            instance would be empty. Construct a fresh ``Results`` (no
            ``cache_path``) when emitting per-bind CSVs.
        """
        columns = self.column_list_by_bind.get(bind_key, [])
        if not columns:
            return ""
        rows = [list(columns)]
        if bind_key is None:
            # Every participant in export_data appears in the default CSV.
            pid_filter = None
        else:
            pid_filter = self._bind_pids.get(bind_key, set())
        for pid, row in self.export_data.items():
            if pid_filter is not None and pid not in pid_filter:
                continue
            rows.append([row.get(column, "") for column in columns])
        return csv_string(rows).rstrip("\n")

    @staticmethod
    def build_filter_from_args(args):
        """Construct a SQLAlchemy filter from request.args query parameters.

        Each toggle, when off, adds a restricting clause; when on, leaves the
        category in the export. Recognized params (literal string 'true' /
        'false', case-insensitive):
          - includeUnfinished (default False) — when False, restrict to finished participants.
          - includeExcluded   (default False) — when False, restrict to non-excluded participants.
          - includeMissing    (default True)  — accepted but currently unused by the filter; kept for API parity.

        Returns: a ClauseElement (db.and_), or None when both toggles are on
        (no filter at all).
        """
        def _parse(name, default):
            value = args.get(name)
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ('true', 'on', '1', 'yes')

        include_unfinished = _parse('includeUnfinished', False)
        include_excluded   = _parse('includeExcluded', False)
        _parse('includeMissing', True)  # accepted for API parity; not used by the filter

        clauses = []
        if not include_unfinished:
            clauses.append(db.Participant.finished == True)
        if not include_excluded:
            clauses.append(db.or_(db.Participant.excludeFromCount == False,
                                  db.Participant.excludeFromCount == None))

        if not clauses:
            return None
        return db.and_(*clauses)

    @staticmethod
    def calculate_results(cache_path):
        """Build a Results, its DataFrame, and per-numeric-column SummaryStats.

        Returns (results, df, summary_stats) where summary_stats is a dict keyed
        by column name, valued by SummaryStats. Filters to finished, non-excluded
        participants. Used by the admin /results and /results_boxplot routes.
        """
        from BOFS.admin.SummaryStats import SummaryStats  # avoid circular at module load
        # Match fetch_progress_summary: legacy rows can have NULL excludeFromCount,
        # which ``== False`` filters out. ``or_`` keeps them in the results.
        results = Results(
            db.and_(
                db.Participant.finished == True,
                db.or_(
                    db.Participant.excludeFromCount == False,
                    db.Participant.excludeFromCount == None,  # noqa: E711
                ),
            ),
            cache_path,
        )
        df = results.build_data_frame()

        summary_stats = {}
        if len(df) > 0:
            df_grouped = df.groupby(by="condition")
            for column in list(df_grouped.head()):
                dtype = df[column].head().dtype.name
                if dtype in ['int64', 'float64', 'bool'] and column not in ['participantID', 'condition', 'duration', 'finished']:
                    summary_stats[column] = SummaryStats(df_grouped, column)

        return results, df, summary_stats
