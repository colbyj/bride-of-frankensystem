from datetime import datetime, timedelta
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import column_property
from sqlalchemy.ext.declarative import declared_attr
from BOFS.util import display_time
from flask import current_app


def create(db):
    class Participant(db.Model):
        __tablename__ = "participant"

        participantID = db.Column(db.Integer, primary_key=True, autoincrement=True)
        mTurkID = db.Column(db.String(50), nullable=False, default="")
        ipAddress = db.Column(db.String(32), nullable=False, default="")
        userAgent = db.Column(db.String(255), nullable=False, default="")
        condition = db.Column(db.Integer, nullable=True, default=0)
        timeStarted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # Starts after consent
        timeEnded = db.Column(db.DateTime, nullable=True)
        finished = db.Column(db.Boolean, nullable=False, default=False)
        excludeFromCount = db.Column(db.Boolean, nullable=False, default=False)
        code = db.Column(db.String(36), nullable=False, default=0)
        lastActiveOn = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        def table(self, name):
            from BOFS.globals import tables


        def questionnaire(self, name, tag=""):
            from BOFS.globals import questionnaires
            qResults = getattr(self, "questionnaire_" + name)

            toConsider = []

            for result in qResults:
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

        def assign_condition(self) -> None:
            numConditions = len(current_app.config['CONDITIONS'])
            if numConditions > 0:
                pCount = [0] * numConditions

                printText = "Total conditions: {}, Counts: ".format(numConditions)

                for condition in range(1, numConditions+1):
                    # Count the participants that have not abandoned the study.
                    if current_app.config['COUNTS_INCLUDE_ABANDONED']:
                        pCount[condition - 1] = db.session.query(db.Participant).\
                            filter(db.Participant.condition == condition,
                                   ~db.Participant.excludeFromCount).\
                            count()
                    else:
                        pCount[condition-1] = db.session.query(db.Participant).\
                            filter(
                                db.and_(db.Participant.condition == condition,
                                        ~db.Participant.is_abandoned,
                                        ~db.Participant.excludeFromCount)
                            ).count()

                    printText += "{}, ".format(pCount[condition-1])

                pCountSorted = sorted(pCount)

                for count in pCountSorted:
                    idx = pCount.index(count)
                    conditionMeta = current_app.config['CONDITIONS'][idx]
                    if 'enabled' not in conditionMeta or conditionMeta['enabled'] == True:
                        self.condition = idx + 1
                        break

                printText += "User put in condition {}.".format(self.condition)
                print(printText)
            else:
                self.condition = None

        def release_condition(self) -> None:
            if self.condition is not None and self.condition > 0:
                self.condition = -self.condition

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


    class Progress(db.Model):
        __tablename__ = "progress"

        participantID = db.Column(db.Integer, db.ForeignKey('participant.participantID'), primary_key=True)
        path = db.Column(db.Text, nullable=False, primary_key=True)
        startedOn = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
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
        timeClicked = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
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
        createdOn = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

        def __repr__(self):
            return '<Session data {0!s}>'.format(self.data)

        @property
        def expired(self) -> bool:
            return self.expiry is None or self.expiry <= datetime.utcnow()

    return Participant, Progress, RadioGridLog, Display, SessionStore

