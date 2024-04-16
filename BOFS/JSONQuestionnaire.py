import os
import json
import re
import pprint
from flask import current_app, request, session, config
from datetime import datetime
from .globals import db


class JSONQuestionnaireColumn(object):
    def __init__(self, definition: dict, question_type: str | None = None):
        self.id = definition['id']
        self.data_type = "string"
        self.default = ""

        if question_type is None and 'questiontype' in definition:
            question_type = definition['questiontype']
        else:
            question_type = "string"

        if question_type.lower() in ["slider", "num_field"]:
            self.data_type = "integer"

        if 'datatype' in definition:
            self.data_type = definition['datatype']

        if self.data_type in ["integer", "float"]:
            self.default = 0

    def get_type_ddl(self):
        if self.data_type == "integer":
            return "INTEGER"
        elif self.data_type == "float":
            return "NUMERIC"
        elif self.data_type == "datetime":
            return "DATETIME"
        elif self.data_type == "boolean":
            return "BOOLEAN"
        else:
            return "TEXT"

    def generate_db_column(self):
        if self.data_type == "integer":
            return db.Column(db.Integer, nullable=False, default=self.default)
        elif self.data_type == "float":
            return db.Column(db.Float, nullable=False, default=self.default)
        elif self.data_type == "datetime":
            return db.Column(db.DateTime, nullable=False, default=self.default)
        elif self.data_type == "boolean":
            return db.Column(db.Boolean, nullable=False, default=self.default)
        else:
            return db.Column(db.Text, nullable=False, default=self.default)


class JSONQuestionnaire(object):
    def __init__(self, directory: str, file_name: str ):
        self.file_name = file_name
        fullPath = os.path.join(directory, file_name + ".json")

        try:
            with open(fullPath) as f:
                self.json_data = json.load(f)
        except ValueError as error:
            raise SyntaxError("ERROR! Unable to parse `%s` questionnaire. Please check that the file contains valid JSON syntax. "
                  "Python reports the following error: `%s`" % (file_name, error))
            self.json_data = None

        self.__fields: list["JSONQuestionnaireColumn"] = []
        self.__calc_fields: list[str] = []
        self.__field_count = 0
        self.db_class : db.Model | None = None

    def get_table_name(self):
        return self.db_class.__tablename__

    def get_calculated_fields(self) -> list[str]:
        return self.__calc_fields

    def fetch_fields(self) -> list["JSONQuestionnaireColumn"]:
        self.__fields: list["JSONQuestionnaireColumn"]= []

        if not self.json_data or 'questions' not in self.json_data:
            print ("ERROR! `%s` questionnaire contains no questions." % self.file_name)
            return

        #print "fetchFields() for " + self.fileName

        for q in self.json_data['questions']:
            if not 'id' in list(q.keys()):
                continue

            # Build up the fields list based on the questionnaire
            if 'q_text' in q and 'questions' not in q:
                q['questions'] = q['q_text']

            if 'questions' in q:
                question_type = q['questiontype']
                for qt in q['questions']:
                    if 'id' in qt:
                        self.__fields.append(JSONQuestionnaireColumn(qt, question_type))
            if 'id' in q:
                self.__fields.append(JSONQuestionnaireColumn(q))

        self.__field_count = len(self.__fields)
        return self.__fields

    def create_db_class(self):
        #print "createDBClass() for " + self.fileName

        if not self.__fields:  # If list is empty
            self.fetch_fields()

        if not self.__calc_fields:
            self.__calc_fields = []

        table_name = str.format(u"questionnaire_{}", self.file_name)

        table_attr = {
            '__tablename__': table_name,
            str.format(u'{0}ID', self.file_name): db.Column(db.Integer, primary_key=True, autoincrement=True),
            'participantID': db.Column(db.Integer, db.ForeignKey("participant.participantID"), nullable=False),
            #'participantID': db.Column(db.Integer),
            'participant': db.relationship("Participant", backref=table_name),
            'tag': db.Column(db.String, nullable=False, default=""),
            'timeStarted': db.Column(db.DateTime, nullable=False, default=db.func.now()),
            'timeEnded': db.Column(db.DateTime, nullable=False, default=db.func.now()),
            'duration': lambda self: (self.timeEnded - self.timeStarted).total_seconds()
        }

        for field in self.__fields:
            table_attr[field.id] = field.generate_db_column()

        if "participant_calculations" in self.json_data:
            def execute_calculation(self, calculation):
                try:
                    return eval(calculation)
                except Exception as e:
                    error = "Unable to add calculated field `{0}` to the export of questionnaire `{1}`. \n" \
                            "The preprocessed calculation string was: `{2}`\n" \
                            "The thrown exception was: {3}".format(field_name, self.__tablename__, calculation, e)
                    print(error)
                    raise Exception(error)

            for field_name, calculation in self.json_data["participant_calculations"].items():
                self.__calc_fields.append(field_name)
                calculation = self.preprocess_calculation_string(calculation)

                table_attr[field_name] = lambda self, calculation=calculation: execute_calculation(self, calculation)

        self.db_class = type(self.file_name, (db.Model,), table_attr)

    # Replace field_name with self.field_name
    def preprocess_calculation_string(self, calculationString):
        for field in self.__fields:
            calculationString = re.sub("{}(?=,|\]|\)|-|\+|/|\*| |$)".
                                       format(field.id), "float(getattr(self, '{}'))".format(field.id), calculationString)

        return calculationString

    def create_blank(self):
        blank = self.db_class()

        for column in blank.__table__.c:
            if column.default:
                setattr(blank, column.name, column.default.arg)
            if column.data_type == db.DateTime:
                setattr(blank, column.name, datetime.min)

        return blank

    def handle_questionnaire(self, tag=""):
        # Check to see if the user has submitted this once already...
        previous = db.session.query(self.db_class).filter(
            self.db_class.participantID == session['participantID'],
            self.db_class.tag == tag
        ).all()

        if previous and len(previous) == 1:
            new_object = previous[0]
        else:
            new_object = self.db_class()

        #print "handleQuestionnaire() for " + self.fileName + "."

        try:
            timeStarted = datetime.strptime(request.form['timeStarted'], "%Y-%m-%d %H:%M:%S.%f")
        except:
            timeStarted = datetime.strptime(request.form['timeStarted'], "%Y-%m-%d %H:%M:%S")

        # For some reason we've lost the fields! add them again
        if not self.__fields or len(self.__fields) == 0 or len(self.__fields) != self.__field_count:
            self.fetch_fields()

        # Log the per-item timing data
        # gridItemClicks
        #request.form['gridItemClicks']

        try:
            for click_event in str(request.form['gridItemClicks']).split(";"):
                if len(click_event) == 0:
                    continue  # There is no data (is it the last line?), so skip it.

                click_event = click_event.replace('\\', "")
                click_event_dict = json.loads(click_event)

                parsed_time = datetime.fromtimestamp(float(click_event_dict['time']))

                new_log = db.RadioGridLog()
                new_log.participantID = session['participantID']
                new_log.questionnaire = self.file_name
                new_log.tag = tag
                new_log.questionID = click_event_dict['id']
                new_log.timeClicked = parsed_time
                new_log.value = click_event_dict['value']

                db.session.add(new_log)

            db.session.commit()

        except:
            pass

        for field in self.__fields:
            #print field

            try:
                value = request.form.get(field.id, None)
                if value is not None:
                    setattr(new_object, field.id, value)
                else:
                    attr = getattr(self.db_class, field.id)
                    default = attr.expression.default.arg
                    setattr(new_object, field.id, default)
            except:
                print("Could not write field " + str(field.id))
            #print("value = {}; set value = {};".format(repr(value), repr(getattr(new_object, field.id))))

        setattr(new_object, 'participantID', session['participantID'])
        setattr(new_object, 'timeStarted', timeStarted)
        setattr(new_object, 'timeEnded', datetime.utcnow())
        setattr(new_object, 'tag', tag)

        db.session.add(new_object)
        db.session.commit()

        if 'ENABLE_LOGGING' in current_app.config and current_app.config['ENABLE_LOGGING'] == True:
            if not os.path.exists("logs"):
                os.makedirs("logs")

            f = open("logs/" + self.file_name + ".txt", "a+")
            f.write("Time = " + str(timeStarted) + "; pID = " + str(session['participantID']) + ";\n" + pprint.pformat(request.form) + "\n\n")

    def get_field(self, id):
        for f in self.__fields:
            if f.id == id:
                return f
        return None

    def fetch_all_data(self):
        return db.session.query(self.db_class).all()

    def fetch_finished_data(self):
        return db.session.query(self.db_class).filter(db.Participant.finished == True).all()

    # Returns a list of the data for a single column, ordered by
    def fetch_column_data(self, column, condition=0, finishedOnly=True):
        #q = None
        #if finishedOnly:
        #    q = db.session.query(self.dbClass).filter(db.Participant.finished == True)
        #else:
        #    q = db.session.query(self.dbClass)

        q = db.session.query(getattr(self.db_class, column)).\
            join(db.Participant,
                 db.and_(
                     getattr(self.db_class, "participantID") == db.Participant.participantID,
                     db.Participant.condition == condition
                 ))

        return q.all()
