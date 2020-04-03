from __future__ import print_function
from __future__ import absolute_import
from builtins import str
from builtins import object
import os
import json
from datetime import datetime
from .globals import db
from flask import current_app, request, session, config
import pprint
from BOFS.util import mean, stdev, std, var, variance, median
import re


class QuestionnaireField(object):
    def __init__(self, id, dataType, reversed=False, labels=[]):
        self.id = id
        self.dataType = dataType
        self.reversed = reversed  # TODO: This is basically depricated now.
        self.labels = labels

    def __repr__(self):
        return "{{'id': {}, 'dataType': {}, 'reversed': {}, 'labels': {}}}".format(
                repr(self.id), repr(self.dataType), repr(self.reversed), repr(self.labels))


class JSONQuestionnaire(object):
    def __init__(self, fileName):
        self.fileName = fileName
        fullPath = os.path.join(current_app.root_path, "questionnaires/" + fileName + ".json")

        try:
            with open(fullPath) as f:
                self.jsonData = json.load(f)
        except ValueError as error:
            print("ERROR! Unable to `%s` questionnaire. Please check that the file contains valid JSON syntax. "
                  "Python reports the following error: `%s`" % (fileName, error))
            self.jsonData = None

        self.fields = []
        self.calcFields = []
        self.dbClass = None
        self.fieldCount = 0

    def fetch_fields(self):
        self.fields = []

        if not self.jsonData or 'questions' not in self.jsonData:
            print ("ERROR! `%s` questionnaire contains no questions." % self.fileName)
            return

        #print "fetchFields() for " + self.fileName

        for q in self.jsonData['questions']:
            if not 'id' in list(q.keys()):
                continue

            #try:
            if q['questiontype'] == "radiogrid":  # Radiogrids will have multiple questions inside of them.
                for qt in q['q_text']:
                    self.fields.append(QuestionnaireField(qt['id'], 'integer', qt.get('reversed', False), q.get('labels', [])))
            elif q['questiontype'] == "checklist":  # checklists also have multiple questions
                for qt in q['questions']:
                    self.fields.append(QuestionnaireField(qt['id'], 'integer'))
            elif q['questiontype'] == "radiolist":  # will always be integer types
                self.fields.append(QuestionnaireField(q['id'], 'integer', False, q.get('labels', [])))
            elif q['questiontype'] in ["slider", "num_field"]:
                self.fields.append(QuestionnaireField(q['id'], 'integer'))
            else:
                #print "self.fields.append(QuestionnaireField(" + q['id'] + ", 'string'))"
                self.fields.append(QuestionnaireField(q['id'], 'string'))
            #except:
            #    print("A very bad error occurred! Restart the server NOW or risk losing data!")

            #pprint.pprint(q)

        self.fieldCount = len(self.fields)
        return self.fields

    def create_db_class(self):
        #print "createDBClass() for " + self.fileName

        if not self.fields:  # If list is empty
            self.fetch_fields()

        if not self.calcFields:
            self.calcFields = []

        tableName = str.format(u"questionnaire_{}", self.fileName)

        tableAttr = {
            '__tablename__': tableName,
            str.format(u'{0}ID', self.fileName): db.Column(db.Integer, primary_key=True, autoincrement=True),
            'participantID': db.Column(db.Integer, db.ForeignKey("participant.participantID"), nullable=False),
            #'participantID': db.Column(db.Integer),
            'participant': db.relationship("Participant", backref=tableName),
            'tag': db.Column(db.String(30), nullable=False, default=""),
            'timeStarted': db.Column(db.DateTime, nullable=False, default=db.func.now()),
            'timeEnded': db.Column(db.DateTime, nullable=False, default=db.func.now()),
            'duration': lambda self: (self.timeEnded - self.timeStarted).total_seconds()
        }

        for field in self.fields:
            if field.dataType == "integer":
                tableAttr[field.id] = db.Column(db.Integer, nullable=False, default=0)
            else:
                tableAttr[field.id] = db.Column(db.Text, nullable=False, default="")

        if "participant_calculations" in self.jsonData:
            def execute_calculation(self, calculation):
                try:
                    return eval(calculation)
                except Exception as e:
                    error = "Unable to add calculated field `{0}` to the export of questionnaire `{1}`. \n" \
                            "The preprocessed calculation string was: `{2}`\n" \
                            "The thrown exception was: {3}".format(field_name, self.__tablename__, calculation, e)
                    print(error)
                    raise Exception(error)

            for field_name, calculation in self.jsonData["participant_calculations"].items():
                self.calcFields.append(field_name)
                calculation = self.preprocess_calculation_string(calculation)

                tableAttr[field_name] = lambda self, calculation=calculation: execute_calculation(self, calculation)

        self.dbClass = type(self.fileName, (db.Model,), tableAttr)

    # Replace field_name with self.field_name
    def preprocess_calculation_string(self, calculationString):
        for field in self.fields:
            calculationString = re.sub("{}(?=,|\]|\)|-|\+|/|\*| |$)".
                                       format(field.id), "getattr(self, '{}')".format(field.id), calculationString)

        return calculationString

    def create_blank(self):
        blank = self.dbClass()

        for column in blank.__table__.c:
            if column.default:
                setattr(blank, column.name, column.default.arg)
            if column.type == db.DateTime:
                setattr(blank, column.name, datetime.min)

        return blank

    def handle_questionnaire(self, tag=""):
        # Check to see if the user has submitted this once already...
        previous = db.session.query(self.dbClass).filter(
            self.dbClass.participantID == session['participantID'],
            self.dbClass.tag == tag
        ).all()

        if previous and len(previous) == 1:
            newObject = previous[0]
        else:
            newObject = self.dbClass()

        #print "handleQuestionnaire() for " + self.fileName + "."

        try:
            timeStarted = datetime.strptime(request.form['timeStarted'], "%Y-%m-%d %H:%M:%S.%f")
        except:
            timeStarted = datetime.strptime(request.form['timeStarted'], "%Y-%m-%d %H:%M:%S")

        # For some reason we've lost the fields! add them again
        if not self.fields or len(self.fields) == 0:
            print("Oh no! We've lost ALL the fields at {}. Running fetchFields() again.".format(str(timeStarted)))
            self.fetch_fields()

        if len(self.fields) != self.fieldCount:
            print("Oh no! We've lost SOME OF the fields at {}. Running fetchFields() again.".format(str(timeStarted)))
            self.fetch_fields()

        # Log the per-item timing data
        # gridItemClicks
        #request.form['gridItemClicks']

        try:
            for clickEvent in str(request.form['gridItemClicks']).split(";"):
                if len(clickEvent) == 0:
                    continue  # There is no data (is it the last line?), so skip it.

                clickEvent = clickEvent.replace('\\', "")
                clickEventDict = json.loads(clickEvent)

                parsedTime = datetime.fromtimestamp(float(clickEventDict['time']))

                newLog = db.RadioGridLog()
                newLog.participantID = session['participantID']
                newLog.questionnaire = self.fileName
                newLog.tag = tag
                newLog.questionID = clickEventDict['id']
                newLog.timeClicked = parsedTime
                newLog.value = clickEventDict['value']

                db.session.add(newLog)

            db.session.commit()

        except:
            pass

        for field in self.fields:
            #print field

            try:
                value = request.form.get(field.id, None)
                if value is not None:
                    setattr(newObject, field.id, value)
                else:
                    attr = getattr(self.dbClass, field.id)
                    default = attr.expression.default.arg
                    setattr(newObject, field.id, default)
            except:
                print("Could not write field " + str(field.id))
            #print("value = {}; set value = {};".format(repr(value), repr(getattr(newObject, field.id))))

        setattr(newObject, 'participantID', session['participantID'])
        setattr(newObject, 'timeStarted', timeStarted)
        setattr(newObject, 'timeEnded', datetime.now())
        setattr(newObject, 'tag', tag)

        db.session.add(newObject)
        db.session.commit()

        if 'ENABLE_LOGGING' in current_app.config and current_app.config['ENABLE_LOGGING'] == True:
            if not os.path.exists("logs"):
                os.makedirs("logs")

            f = open("logs/" + self.fileName + ".txt", "a+")
            f.write("Time = " + str(timeStarted) + "; pID = " + str(session['participantID']) + ";\n" + pprint.pformat(request.form) + "\n\n")

    def get_field(self, id):
        for f in self.fields:
            if f.id == id:
                return f
        return None

    def fetch_all_data(self):
        return db.session.query(self.dbClass).all()

    def fetch_finished_data(self):
        return db.session.query(self.dbClass).filter(db.Participant.finished == True).all()

    # Returns a list of the data for a single column, ordered by
    def fetch_column_data(self, column, condition=0, finishedOnly=True):
        #q = None
        #if finishedOnly:
        #    q = db.session.query(self.dbClass).filter(db.Participant.finished == True)
        #else:
        #    q = db.session.query(self.dbClass)

        q = db.session.query(getattr(self.dbClass, column)).\
            join(db.Participant,
                 db.and_(
                     getattr(self.dbClass, "participantID") == db.Participant.participantID,
                     db.Participant.condition == condition
                 ))

        return q.all()
