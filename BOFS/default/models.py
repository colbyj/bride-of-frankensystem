import functools

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import column_property
from sqlalchemy.ext.declarative import declared_attr
from BOFS.util import display_time, utcnow_naive
from flask import current_app


@functools.lru_cache(maxsize=128)
def _compile_expression(expression):
    """Parse a BOFS expression once per source string. Bounded so a
    runaway loop of unique expressions can't grow the cache without
    bound. Used by :meth:`Participant.evaluate`.
    """
    from BOFS.expressions import parse_page_predicate
    return parse_page_predicate(expression)


class TableAccessor:
    """A participant's view of a JSONTable.

    Returned by :meth:`Participant.table`. Exposes the participant's raw
    rows (``accessor.rows``) and any per-participant aggregates declared
    in the table's ``exports`` block as ordinary attributes
    (``accessor.<export_field>``). Aggregates are computed lazily by
    running the export's SQL aggregation restricted to this participant,
    and the result is memoised on the accessor instance.

    Scalar exports return a single value; ``group_by`` exports return a
    dict keyed by the group value (or by a tuple of values when
    ``group_by`` is a list of columns).

    The accessor proxies ``__iter__``, ``__len__``, ``__getitem__``, and
    ``__bool__`` to ``rows`` so existing template idioms like
    ``{% for row in participant.table('foo') %}`` and
    ``participant.table('foo')|length`` continue to work.
    """

    def __init__(self, participant, name):
        self._participant = participant
        self._name = name

    @property
    def rows(self):
        """The participant's raw rows in the table, as a list of model
        instances. Returns ``[]`` when the participant has no rows."""
        return list(getattr(self._participant, f"table_{self._name}", []) or [])

    @property
    def exports(self):
        """All export aggregates as a dict.

        Scalar exports map to their value; ``group_by`` exports map to a
        nested dict keyed by group value (or tuple of values for
        multi-column ``group_by``).

        Useful for ``{% for k, v in participant.table('foo').exports.items() %}``.
        Each computed value is also memoised on the accessor instance,
        so a subsequent ``accessor.<field>`` access is a dict lookup.
        """
        table = self._jsontable()
        if table is None:
            return {}
        result = {}
        for export in (table.create_exports_dict() or []):
            for fname in (export.get("fields") or {}):
                if fname in result:
                    continue
                value = self._evaluate_export(table, export, fname)
                result[fname] = value
                object.__setattr__(self, fname, value)
        return result

    def _jsontable(self):
        return current_app.tables.get(self._name)

    def _evaluate_export(self, table, export, field_name):
        """Run an export's per-participant SQL aggregation.

        For scalar exports: returns the aggregate value, or ``None`` if
        no rows match (the GROUP BY produces no row, so
        :meth:`Query.first` returns ``None``).

        For ``group_by`` exports: returns a dict mapping each group value
        (or tuple of values for multi-column group_by) to its aggregate.
        Returns an empty dict if the participant has no matching rows.
        """
        from BOFS.globals import db as _db
        table_class = table.db_class
        pid_col = getattr(table_class, "participantID")
        field_expr = export["fields"][field_name]
        group_by = export.get("group_by")

        if group_by:
            if isinstance(group_by, list):
                group_cols = [getattr(table_class, gb) for gb in group_by]
            else:
                group_cols = [getattr(table_class, group_by)]

            query = (
                _db.session.query(*group_cols)
                .select_from(table_class)
                .filter(pid_col == self._participant.participantID)
                .group_by(pid_col, *group_cols)
                .add_columns(_db.literal_column(field_expr).label(field_name))
            )
            filter_expr = export.get("filter")
            if filter_expr:
                query = query.filter(_db.text(filter_expr))
            having_expr = export.get("having")
            if having_expr:
                query = query.having(_db.text(having_expr))

            result = {}
            for row in query.all():
                if len(group_cols) == 1:
                    key = getattr(row, group_cols[0].key)
                else:
                    key = tuple(getattr(row, c.key) for c in group_cols)
                result[key] = getattr(row, field_name, None)
            return result

        query = (
            _db.session.query(table_class)
            .filter(pid_col == self._participant.participantID)
            .group_by(pid_col)
            .add_columns(_db.literal_column(field_expr).label(field_name))
        )
        filter_expr = export.get("filter")
        if filter_expr:
            query = query.filter(_db.text(filter_expr))
        result = query.first()
        if result is None:
            return None
        return getattr(result, field_name, None)

    def __getattr__(self, attr):
        # __getattr__ only fires when the normal attribute lookup misses.
        # Reject dunder probes early so ``hasattr(accessor, '__foo__')``
        # doesn't trigger a Flask context lookup.
        if attr.startswith("_"):
            raise AttributeError(attr)
        table = self._jsontable()
        if table is None:
            raise AttributeError(
                f"No JSONTable named {self._name!r} is loaded."
            )
        exports = table.create_exports_dict() or []
        for export in exports:
            fields = export.get("fields") or {}
            if attr not in fields:
                continue
            value = self._evaluate_export(table, export, attr)
            object.__setattr__(self, attr, value)
            return value
        known = sorted({
            f for e in exports for f in (e.get("fields") or {})
        })
        raise AttributeError(
            f"Table {self._name!r} has no export field {attr!r}. "
            f"Known exports: {', '.join(known) if known else '(none)'}."
        )

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        return self.rows[idx]

    def __contains__(self, item):
        return item in self.rows

    def __bool__(self):
        return bool(self.rows)

    def __repr__(self):
        try:
            pid = self._participant.participantID
        except Exception:
            pid = "?"
        return f"<TableAccessor {self._name!r} for participant {pid}>"


def create(db):
    class Participant(db.Model):
        __tablename__ = "participant"

        participantID = db.Column(db.Integer, primary_key=True, autoincrement=True)
        mTurkID = db.Column(db.String, nullable=False, default="")
        ipAddress = db.Column(db.String, nullable=False, default="")
        userAgent = db.Column(db.String, nullable=False, default="")
        condition = db.Column(db.Integer, nullable=True, default=0)
        timeStarted = db.Column(db.DateTime, nullable=False, default=utcnow_naive)  # Starts after consent
        timeEnded = db.Column(db.DateTime, nullable=True)
        finished = db.Column(db.Boolean, nullable=False, default=False)
        isCrawler = db.Column(db.Boolean, nullable=False, default=False)
        excludeFromCount = db.Column(db.Boolean, nullable=False, default=False)
        code = db.Column(db.String, nullable=False, default=0)
        lastActiveOn = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
        notes = db.Column(db.String, nullable=False, default="")

        def table(self, name):
            """Return a :class:`TableAccessor` for the named JSONTable.

            ``accessor.rows`` is the list of the participant's raw rows
            in the table, and any export field declared in the table's
            ``exports`` block is available as an attribute (computed
            lazily, memoised on the accessor). The accessor itself is
            iterable / lenable / indexable — it proxies those operations
            to ``rows`` so existing patterns like
            ``{% for trial in participant.table('foo') %}`` continue to
            work. Raises :class:`KeyError` if no JSONTable by that name
            is loaded.
            """
            if name not in current_app.tables:
                raise KeyError(
                    f"No table named {name!r}. Known tables: "
                    f"{sorted(current_app.tables) or '(none)'}."
                )
            return TableAccessor(self, name)

        def has_questionnaire(self, name, tag=""):
            """``True`` when the participant has at least one stored
            submission of ``name`` with the given tag.

            ``Participant.questionnaire`` falls back to a blank-default
            row when there is no submission yet, so reading
            ``participant.questionnaire('survey').field`` always
            succeeds. Use ``has_questionnaire`` first when you need to
            distinguish a defaulted row from a real submission.
            """
            results = getattr(self, f"questionnaire_{name}", None) or []
            for r in results:
                if r.tag == tag or (r.tag == u"0" and tag == ""):
                    return True
            return False

        def evaluate(self, expression):
            """Evaluate a BOFS expression against this participant's
            stored data and return the result.

            Uses the same expression syntax as ``show_if`` and
            ``participant_calculations`` — bare field names, dotted
            references like ``qname.tag.field``, ``tables.<name>.<col>``,
            and the reserved name ``condition``. Returns ``None`` when
            the expression can't be parsed or when a referenced
            questionnaire has not been submitted yet, so a template
            ``{% if participant.evaluate(...) %}`` falls through to the
            ``else`` branch instead of raising.
            """
            from BOFS.expressions import (
                ExpressionError,
                build_participant_env,
                default_functions,
                evaluate as _evaluate_ast,
                referenced_fields,
            )
            if not isinstance(expression, str):
                return None
            try:
                ast_node, refs = _compile_expression(expression)
            except ExpressionError:
                return None

            app = current_app._get_current_object()
            env = build_participant_env(
                self.participantID,
                referenced_fields(ast_node),
                refs,
                getattr(app, "questionnaires", {}),
                app.db,
                tables=getattr(app, "tables", {}),
            )
            try:
                return _evaluate_ast(
                    ast_node, env, functions=default_functions()
                )
            except ExpressionError:
                return None

        def questionnaire(self, name, tag=""):
            from BOFS.globals import questionnaires
            q_results = getattr(self, "questionnaire_" + name)

            toConsider = []

            for result in q_results:
                if result.tag == tag or (result.tag == u'0' and tag == ''):
                    toConsider.append(result)

            if len(toConsider) == 1:
                return toConsider[0]

            if len(toConsider) > 1:
                mostRecent = None
                for result in toConsider:
                    if mostRecent is None or mostRecent.timeEnded > result.timeEnded:
                        mostRecent = result

                return mostRecent

            return questionnaires[name].create_blank()

        # Return a dictionary of question ID -> time delta
        def questionnaire_log(self, name, tag="") -> dict:
            q = self.questionnaire(name, tag)

            if tag == "":
                tag = 0

            logs = db.session.query(db.RadioGridLog).filter(
                db.RadioGridLog.participantID == self.participantID,
                db.RadioGridLog.questionnaire == name,
                db.RadioGridLog.tag == tag
            ).order_by(db.RadioGridLog.timeClicked).all()

            result = {}

            prevTime = q.timeStarted

            for log in logs:
                deltaTime = (log.timeClicked - prevTime).total_seconds()
                prevTime = log.timeClicked

                result[log.questionID] = deltaTime

            return result

        @staticmethod
        def balancer_counts():
            """
            Per-condition participant counts used by the balancer.
            Returns list[int] of length len(CONDITIONS); index i = count for condition i+1.
            Honors COUNTS_INCLUDE_ABANDONED and excludeFromCount, matching assign_condition's filter.
            """
            numConditions = len(current_app.config['CONDITIONS'])
            counts = [0] * numConditions
            for condition in range(1, numConditions + 1):
                if current_app.config['COUNTS_INCLUDE_ABANDONED']:
                    counts[condition - 1] = db.session.query(db.Participant).\
                        filter(db.Participant.condition == condition,
                               ~db.Participant.excludeFromCount).\
                        count()
                else:
                    counts[condition - 1] = db.session.query(db.Participant).\
                        filter(
                            db.and_(db.Participant.condition == condition,
                                    ~db.Participant.is_abandoned,
                                    ~db.Participant.excludeFromCount)
                        ).count()
            return counts

        @classmethod
        def compute_organic_condition(cls):
            """
            Returns the condition integer the balancer would pick right now,
            without mutating any participant. Returns None if no conditions are
            configured, or if no enabled condition can be selected.
            """
            numConditions = len(current_app.config['CONDITIONS'])
            if numConditions == 0:
                return None

            pCount = cls.balancer_counts()
            for count in sorted(pCount):
                idx = pCount.index(count)
                conditionMeta = current_app.config['CONDITIONS'][idx]
                if 'enabled' not in conditionMeta or conditionMeta['enabled'] == True:
                    return idx + 1
            return None

        def assign_condition(self) -> None:
            if self.check_useragent_for_crawler():
                return  # This seems to be a crawler; don't assign a condition

            numConditions = len(current_app.config['CONDITIONS'])
            if numConditions == 0:
                self.condition = None
                return

            # If a CONDITIONS_FROM_CSV / CONDITIONS_FROM_DB source is configured
            # and we already know the participant's external ID, look up first.
            # An ID that's set but not present in the source is a hard error
            # (raised below) — we deliberately don't fall back to the balancer.
            from BOFS.services.condition_lookup import (
                ConditionLookupMiss,
                ConditionLookupService,
            )
            if ConditionLookupService.is_configured() and self.mTurkID:
                looked_up = ConditionLookupService.lookup(self.mTurkID)
                if looked_up is not None:
                    self.condition = looked_up
                    return
                raise ConditionLookupMiss(self.mTurkID)

            pCount = type(self).balancer_counts()
            self.condition = type(self).compute_organic_condition()

            printText = "Total conditions: {}, Counts: ".format(numConditions)
            printText += ", ".join(str(c) for c in pCount)
            printText += ". User put in condition {}.".format(self.condition)
            print(printText)

        @hybrid_property
        def duration(self) -> int:
            if self.timeEnded is None:
                return 0
            return (self.timeEnded - self.timeStarted).total_seconds()
        
        @duration.expression
        def duration(cls):
            return db.case(
                (cls.timeEnded == None, None),
                else_=(db.func.julianday(cls.timeEnded) - db.func.julianday(cls.timeStarted)) * 86400
            ).label('duration')

        @declared_attr
        def is_in_progress(cls):
            return column_property(
                db.and_(
                    ~cls.finished,
                    (1440.0 * (db.func.julianday(db.func.current_timestamp()) - db.func.julianday(cls.lastActiveOn)) <=
                     current_app.config['ABANDONED_MINUTES'])
                ).label('is_in_progress')
            )

        @declared_attr
        def is_abandoned(cls):
            return column_property(
                db.and_(
                    ~cls.finished,
                    (1440.0 * (db.func.julianday(db.func.current_timestamp()) - db.func.julianday(cls.lastActiveOn)) >
                     current_app.config['ABANDONED_MINUTES'])  # 1440 is minutes per day
                ).label('is_abandoned')
            )

        def display_duration(self) -> str:
            """
            display the time taken or status
            :return:
            """

            if self.timeEnded is None:
                if self.is_in_progress:
                    return "In Progress"
                else:
                    return "Abandoned"

            else:
                seconds = (self.timeEnded - self.timeStarted).total_seconds()
                return display_time(seconds)

        def check_useragent_for_crawler(self):
            self.isCrawler = current_app.crawler_detect.isCrawler(self.userAgent)

            if self.isCrawler:
                self.excludeFromCount = True

            return self.isCrawler


    class Progress(db.Model):
        __tablename__ = "progress"

        participantID = db.Column(db.Integer, db.ForeignKey('participant.participantID'), primary_key=True)
        path = db.Column(db.Text, nullable=False, primary_key=True)
        startedOn = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
        submittedOn = db.Column(db.DateTime, nullable=True)

        def display_duration(self) -> str:
            if self.submittedOn is None:
                return "..."
            else:
                seconds = (self.submittedOn - self.startedOn).total_seconds()
                if seconds > 60:
                    return str("{:.0f}:{:02.0f}").format((seconds / 60), (seconds % 60))
                return str(int(seconds))


    class RadioGridLog(db.Model):
        __tablename__ = "radio_grid_log"

        radioGridLog = db.Column(db.Integer, primary_key=True, autoincrement=True)
        participantID = db.Column(db.Integer, db.ForeignKey('participant.participantID'))
        timeClicked = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
        questionnaire = db.Column(db.String, nullable=False, default="")
        tag = db.Column(db.String, nullable=False, default="")
        questionID = db.Column(db.String, nullable=False, default="")
        value = db.Column(db.String, nullable=False, default="")


    class Display(db.Model):
        __tablename__ = "display"

        logDisplayID = db.Column(db.Integer, primary_key=True, autoincrement=True)
        participantID = db.Column(db.Integer, db.ForeignKey('participant.participantID'))
        dppx = db.Column(db.Float, nullable=False, default=0.0)
        screenWidth = db.Column(db.Integer, nullable=False, default=0)
        screenHeight = db.Column(db.Integer, nullable=False, default=0)
        innerWidth = db.Column(db.Integer, nullable=False, default=0)
        innerHeight = db.Column(db.Integer, nullable=False, default=0)


    class SessionStore(db.Model):
        __tablename__ = "session_store"

        sessionID = db.Column(db.String(255), primary_key=True)
        participantID = db.Column(db.Integer, db.ForeignKey('participant.participantID'), nullable=True)
        mTurkID = db.Column(db.Text, nullable=True)
        data = db.Column(db.Text)
        expiry = db.Column(db.DateTime)
        createdOn = db.Column(db.DateTime, nullable=False, default=utcnow_naive)

        def __repr__(self):
            return '<Session data {0!s}>'.format(self.data)

        @property
        def expired(self) -> bool:
            return self.expiry is None or self.expiry <= utcnow_naive()


    class AppMeta(db.Model):
        __tablename__ = "app_meta"

        key = db.Column(db.String(64), primary_key=True)
        value = db.Column(db.Text, nullable=False)


    class BannedIp(db.Model):
        __tablename__ = "banned_ip"

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        ipAddress = db.Column(db.String, nullable=False, index=True)
        bannedAt = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
        expiresAt = db.Column(db.DateTime, nullable=True)
        reason = db.Column(db.String, nullable=False, default="admin_login")
        failCount = db.Column(db.Integer, nullable=False, default=0)
        notes = db.Column(db.String, nullable=True)

        @property
        def is_active(self) -> bool:
            if self.expiresAt is None:
                return True
            return self.expiresAt > utcnow_naive()


    class LoginAttempt(db.Model):
        __tablename__ = "login_attempt"

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        ipAddress = db.Column(db.String, nullable=False, index=True)
        attemptedAt = db.Column(db.DateTime, nullable=False, default=utcnow_naive, index=True)


    class AdminTrustedIp(db.Model):
        __tablename__ = "admin_trusted_ip"

        ipAddress = db.Column(db.String, primary_key=True)
        firstSeenAt = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
        lastSeenAt = db.Column(db.DateTime, nullable=False, default=utcnow_naive)


    return Participant, Progress, RadioGridLog, Display, SessionStore, AppMeta, BannedIp, LoginAttempt, AdminTrustedIp

