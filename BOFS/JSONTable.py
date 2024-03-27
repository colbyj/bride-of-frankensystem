import os
import json
from datetime import datetime
from .globals import db
from flask import current_app, request, session, config, jsonify


class JSONTable(object):
    def __init__(self, directory: str, file_name: str):
        self.directory = directory
        self.file_name = file_name
        fullPath = os.path.join(directory, file_name + ".json")

        try:
            with open(fullPath) as f:
                self.json_data = json.load(f)
        except ValueError as error:
            print("ERROR! Unable to parse `%s` table definition. Please check that the file contains valid JSON syntax. "
                  "Python reports the following error: `%s`" % (file_name, error))
            self.json_data = None

        self.db_class = None

    def create_db_class(self):
        table_name = self.file_name

        table_attr = {
            '__tablename__': table_name,
            str.format(u'{0}ID', self.file_name): db.Column(db.Integer, primary_key=True, autoincrement=True),
            'participantID': db.Column(db.Integer, db.ForeignKey("participant.participantID"), nullable=False),
            'timeSubmitted': db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        }

        for column in self.json_data['columns']:
            column_details = self.json_data['columns'][column]
            if 'type' in column_details:
                if column_details['type'] == "integer":
                    default = 0 if 'default' not in column_details else column_details['default']
                    table_attr[column] = db.Column(db.Integer, nullable=False, default=default)
                elif column_details['type'] == "float":
                    default = 0 if 'default' not in column_details else column_details['default']
                    table_attr[column] = db.Column(db.Float, nullable=False, default=default)
                elif column_details['type'] == "datetime":
                    default = datetime.min if 'default' not in column_details else column_details['default']
                    table_attr[column] = db.Column(db.DateTime, nullable=False, default=default)
                elif column_details['type'] == "boolean":
                    default = False if 'default' not in column_details else column_details['default']
                    table_attr[column] = db.Column(db.Boolean, nullable=False, default=default)
                else:
                    default = "" if 'default' not in column_details else column_details['default']
                    table_attr[column] = db.Column(db.Text, nullable=False, default=default)
            else:
                default = "" if 'default' not in column_details else column_details['default']
                table_attr[column] = db.Column(db.Text, nullable=False, default=default)

        self.db_class = type(self.file_name, (db.Model,), table_attr)

    def create_exports_dict(self):
        if 'exports' not in self.json_data:
            return None

        exports_dict = []
        if len(self.json_data['exports']) > 0:
            for export_definition in self.json_data['exports']:
                export_definition['table'] = self.file_name
                exports_dict.append(export_definition)

        return exports_dict

    def row_to_dict(self, row):
        result = {}

        for column in self.json_data['columns']:
            column_details = self.json_data['columns'][column]
            value = getattr(row, column)

            if "type" in column_details:
                if column_details['type'] == "integer":
                    result[column] = int(value)
                elif column_details['type'] == "float":
                    result[column] = float(value)
                elif column_details['type'] == "boolean":
                    result[column] = bool(value)
                else:
                    result[column] = str(value)
            else:
                result[column] = str(value)

        return result

    def handle_post(self):
        entry = self.db_class()
        entry.participantID = session['participantID']

        data = request.json

        for column in self.json_data['columns']:
            if column in data:
                columnDetails = self.json_data['columns'][column]
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
        q = db.session.query(self.db_class).\
            filter(self.db_class.participantID == session['participantID'])

        # If there are any GET arguments (e.g., ?arg=value), then try to apply them as simple filters
        for arg in request.args:
            column = getattr(self.db_class, arg)
            q = q.filter(db.cast(column, db.Text) == request.args[arg])

        results = q.all()

        # Turn the result of the query into a list of dictionaries.
        out = [self.row_to_dict(row) for row in results]

        return jsonify(out)

