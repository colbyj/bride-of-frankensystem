import os
import json
from datetime import datetime
from .globals import db
from .util import utcnow_naive
from flask import current_app, request, session, config, jsonify, abort


def _coerce_bool(value):
    """Coerce a value to bool for a boolean column.

    - Native bool: returned as-is.
    - int/float: standard bool() semantics.
    - str: case-insensitive lookup; raises ValueError for unrecognised strings.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lower = value.lower()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off", ""):
            return False
        raise ValueError(f"Cannot coerce {value!r} to bool")
    raise ValueError(f"Cannot coerce {value!r} to bool")


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
            elif column_details['type'] == "json":
                self.data_type = "json"
                self.default = None
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
            # covers "string", "json", and the empty-string fallback
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
        elif self.data_type == "json":
            # Nullable TEXT — None is a valid "not yet set" state and avoids
            # the NULL-vs-empty-string ambiguity that plagues non-nullable TEXT.
            return db.Column(db.Text, nullable=True, default=None)
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
            'timeSubmitted': db.Column(db.DateTime, nullable=False, default=utcnow_naive)
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

        # Shallow-copy each export definition before annotating it with the
        # table name. Mutating self.json_data in place is unsafe because the
        # source dict is shared with whoever loaded the JSON file (and a
        # second call to this method would otherwise see the previous run's
        # 'table' key already in place).
        exports_dict = []
        for export_definition in self.json_data['exports']:
            export_copy = dict(export_definition)
            export_copy['table'] = self.file_name
            exports_dict.append(export_copy)

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
                elif column_details['type'] == "datetime":
                    result[column] = value.isoformat() if value is not None else None
                elif column_details['type'] == "json":
                    if value and isinstance(value, str):
                        result[column] = json.loads(value)
                    else:
                        result[column] = None
                else:
                    result[column] = str(value)
            else:
                result[column] = str(value)

        return result

    def _apply_data_to_entry(self, entry, data):
        """Populate a db entry object from a data dict.

        Raises ValueError/TypeError for bad values; the caller is responsible
        for rolling back the session on any exception.
        """
        for column in self.json_data['columns']:
            if column not in data:
                continue

            columnDetails = self.json_data['columns'][column]
            value = data[column]

            if "type" not in columnDetails:
                setattr(entry, column, value)
                continue

            col_type = columnDetails['type']

            if col_type == "integer":
                setattr(entry, column, int(value))
            elif col_type == "float":
                setattr(entry, column, float(value))
            elif col_type == "boolean":
                try:
                    setattr(entry, column, _coerce_bool(value))
                except ValueError:
                    abort(400, description=f"Invalid boolean value for column '{column}': {value!r}")
            elif col_type == "json":
                if isinstance(value, str):
                    # form-encoded path: validate that the string is valid JSON
                    try:
                        json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        abort(400, description=f"Invalid JSON string for column '{column}'")
                    setattr(entry, column, value)
                else:
                    # already a Python object (from request.json); serialise it
                    setattr(entry, column, json.dumps(value))
            else:
                setattr(entry, column, value)

    def handle_post(self):
        # Without a participantID we can't attribute the row to anyone —
        # reject early rather than KeyError mid-loop.
        if 'participantID' not in session:
            abort(401)

        # Prefer JSON when the body parses; fall back to form data otherwise.
        # silent=True returns None instead of raising on parse error or when
        # the Content-Type isn't application/json.
        data = request.get_json(silent=True)
        if data is None:
            data = request.form

        if isinstance(data, list):
            # Batch insert: each element must be a dict; any failure rolls back.
            try:
                for item in data:
                    if not isinstance(item, dict):
                        abort(400, description="Each element of a batch POST must be a JSON object (dict).")
                    entry = self.db_class()
                    entry.participantID = session['participantID']
                    self._apply_data_to_entry(entry, item)
                    db.session.add(entry)
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
        else:
            # Single insert (JSON object or form-encoded)
            entry = self.db_class()
            entry.participantID = session['participantID']
            self._apply_data_to_entry(entry, data)
            db.session.add(entry)
            db.session.commit()

        return "", 204

    def handle_get(self):
        if 'participantID' not in session:
            abort(401)

        q = db.session.query(self.db_class).\
            filter(self.db_class.participantID == session['participantID'])

        # If there are any GET arguments (e.g., ?arg=value), apply them as
        # simple filters. Allow-list against the researcher-declared columns
        # so a probe like ``?_sa_instance_state=x`` hits a clean 400 instead
        # of leaking a 500 with the internal attribute name.
        allowed_columns = set(self.json_data.get('columns', {})) if self.json_data else set()
        for arg in request.args:
            if arg not in allowed_columns:
                abort(400, description=f"Unknown filter column: {arg!r}")
            column = getattr(self.db_class, arg)
            q = q.filter(db.cast(column, db.Text) == request.args[arg])

        results = q.all()

        # Turn the result of the query into a list of dictionaries.
        out = [self.row_to_dict(row) for row in results]

        return jsonify(out)

