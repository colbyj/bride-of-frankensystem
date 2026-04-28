from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import column_property
from sqlalchemy.ext.declarative import declared_attr
from BOFS.util import display_time, utcnow_naive
from flask import current_app


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
            return getattr(self, "table_" + name)


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

    return Participant, Progress, RadioGridLog, Display, SessionStore, AppMeta

