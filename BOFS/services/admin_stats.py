from typing import Tuple, List, Any, Dict
from flask import current_app
from BOFS.globals import db


class AdminStatsService:
    """Stateless service for admin progress queries."""

    @staticmethod
    def fetch_progress() -> Tuple[List[Dict], List]:
        """Per-participant progress across PAGE_LIST entries (excluding consent and end).

        Returns (pages, progress) where:
          - pages: list of page-list entries (each dict has 'name', 'path').
          - progress: list of result rows from the outer-joined query —
            each row contains the Participant entity plus one Progress entity
            (or None) per page, in the order of `pages`.

        The page list is built by iterating all conditions (or ``condition=0``
        when no conditions are configured) with ``participant_id=None`` so that
        every column that any participant could possibly have visited appears
        in the table - including pages behind a ``conditional_routing`` block
        or a ``show_if`` expression. Columns are deduplicated by
        ``(path, occurrence)`` across all conditions so that a page visited
        twice (e.g. duplicate instructions) shows distinct timing columns.
        Per-participant filtering happens in the join: a participant who never
        visited a given page simply has a NULL Progress row in that column.
        """
        condition_count = len(current_app.config.get('CONDITIONS', []) or [])
        conditions = list(range(1, condition_count + 1)) if condition_count > 0 else [0]

        columns = []
        seen_keys = set()
        for condition in conditions:
            flat = current_app.page_list.flat_page_list(
                condition=condition, participant_id=None
            )
            for page, occ in current_app.page_list.annotate_occurrences(flat):
                path = page['path']
                if path == "consent" or path == "end" or path.startswith("end/"):
                    continue
                key = (path, occ)
                if key not in seen_keys:
                    columns.append((page, occ))
                    seen_keys.add(key)

        pages = [page for page, _ in columns]
        progress = db.session.query(db.Participant).filter(db.Participant.isCrawler == False)

        for idx, (page, occ) in enumerate(columns):
            pp = db.aliased(db.Progress, name=f"_pp_{idx}")
            progress = progress.outerjoin(pp, db.and_(
                pp.participantID == db.Participant.participantID,
                pp.path == page['path'],
                pp.occurrence == occ,
            )).add_entity(
                pp
            )

        progress = progress.all()
        return pages, progress

    @staticmethod
    def fetch_progress_summary() -> Tuple[List[Any], Any]:
        """Aggregated participant counts and durations.

        Returns (summary_groups, summary) where:
          - summary_groups: rows grouped by Participant.condition with
            count / countAbandoned / countInProgress / countFinished /
            avg-duration columns.
          - summary: a single row with overall counts and min/max/avg duration.
        """
        summary_groups = db.session.query(
            db.Participant.condition,
            db.func.count(db.Participant.participantID).label('count'),
            db.func.sum(db.cast(db.Participant.is_abandoned, db.Integer)).label('countAbandoned'),
            db.func.sum(db.cast(db.Participant.is_in_progress, db.Integer)).label('countInProgress'),
            db.func.sum(db.cast(db.Participant.finished, db.Integer)).label('countFinished'),
            db.func.avg(db.Participant.duration).label('minutes')). \
            filter(db.or_(~db.Participant.excludeFromCount, db.Participant.excludeFromCount == None)). \
            group_by(db.Participant.condition).all()

        summary = db.session.query(
            db.func.count(db.Participant.participantID).label('count'),
            db.func.sum(db.cast(db.Participant.is_abandoned, db.Integer)).label('countAbandoned'),
            db.func.sum(db.cast(db.Participant.is_in_progress, db.Integer)).label('countInProgress'),
            db.func.sum(db.cast(db.Participant.finished, db.Integer)).label('countFinished'),
            db.func.min(db.Participant.duration).label('minSeconds'),
            db.func.max(db.Participant.duration).label('maxSeconds'),
            db.func.avg(db.Participant.duration).label('seconds')). \
            filter(db.or_(~db.Participant.excludeFromCount, db.Participant.excludeFromCount == None)). \
            one()

        return summary_groups, summary

    @staticmethod
    def fetch_end_reason_counts() -> List[Tuple[Any, int]]:
        """Participant counts grouped by ``end_reason``.

        Returns a list of ``(end_reason, count)`` tuples ordered by count
        descending. ``end_reason`` is ``None`` for participants who never
        reached ``/end/<reason>`` (i.e. abandoned mid-study).

        Does not filter by ``excludeFromCount`` — admins typically want
        to see all participants here, including bots that were
        auto-excluded, since the whole point of the widget is to surface
        per-reason intake patterns.
        """
        rows = db.session.query(
            db.Participant.end_reason,
            db.func.count(db.Participant.participantID).label('count'),
        ).group_by(db.Participant.end_reason).all()
        return sorted(rows, key=lambda r: (-r.count, r.end_reason or ""))
