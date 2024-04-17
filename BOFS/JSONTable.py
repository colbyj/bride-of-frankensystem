import os
import json
from datetime import datetime
from .globals import db
from flask import current_app, request, session, config, jsonify


class JSONTableColumn:
    def __init__(self, column_name, column_details):
        self.name = column_name
        self.data_type = ""
        self.default = ""

        if 'type' in column_details:
            if column_details['type'] == "integer":
                self.data_type = "integer"
                self.default = 0 if 'default' not in column_details else column_details['default']
            elif column_details['type'] == "float":
                self.data_type = "float"
                self.default = 0 if 'default' not in column_details else column_details['default']
            elif column_details['type'] == "datetime":
                self.data_type = "datetime"
                self.default = datetime.min if 'default' not in column_details else column_details['default']
            elif column_details['type'] == "boolean":
                self.data_type = "boolean"
                self.default = False if 'default' not in column_details else column_details['default']
            else:
                self.data_type = "string"
                self.default = "" if 'default' not in column_details else column_details['default']

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
            return  db.Column(db.DateTime, nullable=False, default=self.default)
        elif self.data_type == "boolean":
            return db.Column(db.Boolean, nullable=False, default=self.default)
        else:
            return db.Column(db.Text, nullable=False, default=self.default)


class JSONTable(object):
    def __init__(self, directory: str, file_name: str):
        self.__columns: list["JSONTableColumn"] = []
        self.directory = directory
        self.file_name = file_name
        fullPath = os.path.join(directory, file_name + ".json")

        self.json_data: dict = {}

        try:
            with open(fullPath) as f:
                self.json_data = json.load(f)
        except ValueError as error:
            print("ERROR! Unable to parse `%s` table definition. Please check that the file contains valid JSON syntax. "
                  "Python reports the following error: `%s`" % (file_name, error))
            self.json_data = None

        self.db_class = None

    def get_columns(self) -> list["JSONTableColumn"]:
        return self.__columns

    def create_db_class(self):
        table_name = "table_" + self.file_name

        table_attr = {
            '__tablename__': table_name,
            str.format(u'{0}ID', self.file_name): db.Column(db.Integer, primary_key=True, autoincrement=True),
            'participantID': db.Column(db.Integer, db.ForeignKey("participant.participantID"), nullable=False),
            'participant': db.relationship("Participant", backref=table_name),
            'timeSubmitted': db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        }

        for column in self.json_data['columns']:
            column_details = self.json_data['columns'][column]
            new_column = JSONTableColumn(column, column_details)
            self.__columns.append(new_column)

            table_attr[column] = new_column.generate_db_column()

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

        try:
            data = request.json
        except:
            data = request.form

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

