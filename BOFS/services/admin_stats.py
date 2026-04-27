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
        """
        pages = [p for p in current_app.page_list.flat_page_list()
                 if p['path'] not in ("end", "consent")]
        progress = db.session.query(db.Participant).filter(db.Participant.isCrawler == False)

        for page in pages:
            pp = db.aliased(db.Progress, name=page['path'])
            progress = progress.outerjoin(pp, db.and_(
                pp.participantID == db.Participant.participantID,
                pp.path == page['path']
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
