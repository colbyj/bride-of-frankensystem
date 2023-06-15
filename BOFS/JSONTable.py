import os
import json
from datetime import datetime
from .globals import db
from flask import current_app, request, session, config, jsonify


class JSONTable(object):
    def __init__(self, fileName):
        self.fileName = fileName
        fullPath = os.path.join(current_app.root_path, "tables/" + fileName + ".json")

        try:
            with open(fullPath) as f:
                self.jsonData = json.load(f)
        except ValueError as error:
            print("ERROR! Unable to parse `%s` table definition. Please check that the file contains valid JSON syntax. "
                  "Python reports the following error: `%s`" % (fileName, error))
            self.jsonData = None

        self.dbClass = None

    def create_db_class(self):
        tableName = self.fileName

        tableAttr = {
            '__tablename__': tableName,
            str.format(u'{0}ID', self.fileName): db.Column(db.Integer, primary_key=True, autoincrement=True),
            'participantID': db.Column(db.Integer, db.ForeignKey("participant.participantID"), nullable=False),
            'timeSubmitted': db.Column(db.DateTime, nullable=False, default=db.func.now())
        }

        for column in self.jsonData['columns']:
            columnDetails = self.jsonData['columns'][column]
            if 'type' in columnDetails:
                if columnDetails['type'] == "integer":
                    default = 0 if 'default' not in columnDetails else columnDetails['default']
                    tableAttr[column] = db.Column(db.Integer, nullable=False, default=default)
                elif columnDetails['type'] == "float":
                    default = 0 if 'default' not in columnDetails else columnDetails['default']
                    tableAttr[column] = db.Column(db.Float, nullable=False, default=default)
                elif columnDetails['type'] == "datetime":
                    default = datetime.min if 'default' not in columnDetails else columnDetails['default']
                    tableAttr[column] = db.Column(db.DateTime, nullable=False, default=default)
                elif columnDetails['type'] == "boolean":
                    default = False if 'default' not in columnDetails else columnDetails['default']
                    tableAttr[column] = db.Column(db.Boolean, nullable=False, default=default)
                else:
                    default = "" if 'default' not in columnDetails else columnDetails['default']
                    tableAttr[column] = db.Column(db.Text, nullable=False, default=default)
            else:
                default = "" if 'default' not in columnDetails else columnDetails['default']
                tableAttr[column] = db.Column(db.Text, nullable=False, default=default)

        self.dbClass = type(self.fileName, (db.Model,), tableAttr)

    def create_exports_dict(self):
        if 'exports' not in self.jsonData:
            return None

        exports_dict = []
        if len(self.jsonData['exports']) > 0:
            for export_definition in self.jsonData['exports']:
                export_definition['table'] = self.fileName
                exports_dict.append(export_definition)

        return exports_dict

    def row_to_dict(self, row):
        result = {}

        for column in self.jsonData['columns']:
            columnDetails = self.jsonData['columns'][column]
            value = getattr(row, column)

            if "type" in columnDetails:
                if columnDetails['type'] == "integer":
                    result[column] = int(value)
                elif columnDetails['type'] == "float":
                    result[column] = float(value)
                elif columnDetails['type'] == "boolean":
                    result[column] = bool(value)
                else:
                    result[column] = str(value)
            else:
                result[column] = str(value)

        return result

    def handle_post(self):
        entry = self.dbClass()
        entry.participantID = session['participantID']

        data = request.json

        for column in self.jsonData['columns']:
            if column in data:
                columnDetails = self.jsonData['columns'][column]
                value = data[column]

                if "type" in columnDetails:
                    if columnDetails['type'] == "integer":
                        setattr(entry, column, int(value))
                    elif columnDetails['type'] == "float":
                        setattr(entry, column, float(value))
                    elif columnDetails['type'] == "boolean":
                        setattr(entry, column, bool(value))
                    else:
                        setattr(entry, column, value)
                else:
                    setattr(entry, column, value)

        db.session.add(entry)
        db.session.commit()

        return ""

    def handle_get(self):
        q = db.session.query(self.dbClass).\
            filter(self.dbClass.participantID == session['participantID'])

        # If there are any GET arguments (e.g., ?arg=value), then try to apply them as simple filters
        for arg in request.args:
            column = getattr(self.dbClass, arg)
            q = q.filter(db.cast(column, db.Text) == request.args[arg])

        results = q.all()

        # Turn the result of the query into a list of dictionaries.
        out = [self.row_to_dict(row) for row in results]

        return jsonify(out)

