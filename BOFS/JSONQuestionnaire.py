import os
import json
from typing import Union
from datetime import datetime
from sqlalchemy import inspect as sa_inspect
from .globals import db
from .expressions import (
    ExpressionError,
    default_functions,
    evaluate as expr_evaluate,
    parse_with_field_ids,
    referenced_fields,
)
from .sanitizer import sanitize_questionnaire_json
from .validation import EXPANDED_TYPES


def _normalize_type_name(sa_type) -> str:
    """Normalize a SQLAlchemy reflected type to a canonical name for comparison."""
    type_name = type(sa_type).__name__.upper()
    if type_name in ('INTEGER', 'SMALLINTEGER', 'BIGINTEGER'):
        return 'INTEGER'
    elif type_name in ('FLOAT', 'REAL', 'NUMERIC', 'DECIMAL'):
        return 'FLOAT'
    elif type_name in ('TEXT', 'VARCHAR', 'STRING', 'NVARCHAR', 'CHAR'):
        return 'TEXT'
    elif type_name in ('DATETIME', 'TIMESTAMP'):
        return 'DATETIME'
    elif type_name == 'BOOLEAN':
        return 'BOOLEAN'
    return type_name


# Maps JSONQuestionnaireColumn.data_type to normalized type names
_JSON_TYPE_TO_NORMALIZED = {
    'integer': 'INTEGER',
    'float': 'FLOAT',
    'string': 'TEXT',
    'datetime': 'DATETIME',
    'boolean': 'BOOLEAN',
}


def _types_compatible(db_type, json_data_type: str) -> bool:
    """Check if a reflected DB column type is compatible with a JSON field's data_type."""
    db_normalized = _normalize_type_name(db_type)
    json_normalized = _JSON_TYPE_TO_NORMALIZED.get(json_data_type, 'TEXT')
    return db_normalized == json_normalized


class JSONQuestionnaireColumn(object):
    def __init__(self, definition: dict, question_type: Union[str, None] = None):
        self.id = definition['id']
        self.data_type = "string"
        self.default = ""

        if question_type is None:
            if 'questiontype' in definition:
                question_type = definition['questiontype']
            else:
                question_type = "string"

        if question_type.lower() in ["slider", "num_field", "checklist"]:
            self.data_type = "integer"

        if question_type.lower() == "picture_select":
            images = definition.get('images', [])
            values = [img.get('value') for img in images
                      if isinstance(img, dict) and 'value' in img]
            if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
                self.data_type = "integer"
            elif values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
                self.data_type = "float"

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
    def __init__(self, directory: str, file_name: str, is_in_db: bool):
        self.is_in_db = is_in_db
        self.file_name = file_name
        fullPath = os.path.join(directory, file_name + ".json")

        try:
            with open(fullPath) as f:
                self.json_data = json.load(f)
        except ValueError as error:
            raise SyntaxError("ERROR! Unable to parse `%s` questionnaire. Please check that the file contains valid JSON syntax. "
                  "Python reports the following error: `%s`" % (file_name, error))

        # Strip disallowed HTML from researcher-authored text fields up front
        # so every consumer (template render, admin preview, exports) sees the
        # cleaned content. Intentional code-injection slots (q.code) are left
        # alone — see BOFS/sanitizer.py.
        sanitize_questionnaire_json(self.json_data)

        self.__fields: list["JSONQuestionnaireColumn"] = []
        self.__calc_fields: list[str] = []
        self.db_class : db.Model | None = None

    def get_table_name(self):
        return self.db_class.__tablename__

    def get_calculated_fields(self) -> list[str]:
        return self.__calc_fields

    def fetch_fields(self) -> list["JSONQuestionnaireColumn"]:
        if self.__fields:
            return self.__fields

        if not self.json_data or 'questions' not in self.json_data:
            print ("ERROR! `%s` questionnaire contains no questions." % self.file_name)
            return self.__fields

        for q in self.json_data['questions']:
            # Build up the fields list based on the questionnaire
            if 'q_text' in q and 'questions' not in q:
                q['questions'] = q['q_text']

            if 'questions' in q:
                question_type = q['questiontype']
                for qt in q['questions']:
                    if 'id' in qt:
                        self.__fields.append(JSONQuestionnaireColumn(qt, question_type))

            if 'id' in q:
                qtype = q.get('questiontype')
                if qtype in EXPANDED_TYPES:
                    for suffix, dtype in EXPANDED_TYPES[qtype]:
                        self.__fields.append(JSONQuestionnaireColumn(
                            {'id': q['id'] + suffix, 'datatype': dtype}))
                else:
                    self.__fields.append(JSONQuestionnaireColumn(q))

        return self.__fields

    def compile_show_if(self) -> None:
        """Parse any ``show_if`` predicate strings on top-level questions into
        the engine's JSON AST and attach them as ``_show_if_ast`` on the
        question dict so the renderer can emit them without re-parsing.

        Raises if a predicate is unparseable — show_if errors should fail
        loudly at app startup, not silently at request time.
        """
        if not self.__fields:
            self.fetch_fields()

        if not self.json_data or 'questions' not in self.json_data:
            return

        field_ids = [f.id for f in self.__fields]

        for question in self.json_data['questions']:
            expr = question.get('show_if')
            if expr is None:
                continue
            if not isinstance(expr, str) or not expr.strip():
                raise Exception(
                    f"show_if on questionnaire `{self.file_name}` must be a "
                    f"non-empty string expression, got {expr!r}"
                )
            try:
                ast_node = parse_with_field_ids(expr, field_ids)
            except ExpressionError as e:
                raise Exception(
                    f"Unable to parse show_if on questionnaire "
                    f"`{self.file_name}` for question "
                    f"`{question.get('id', '<no id>')}`. "
                    f"Expression: `{expr}`. {e}"
                )
            question['_show_if_ast'] = ast_node

    def create_db_class(self):
        #print "createDBClass() for " + self.fileName

        if not self.__fields:  # If list is empty
            self.fetch_fields()

        self.compile_show_if()

        if not self.__calc_fields:
            self.__calc_fields = []

        table_name = f"questionnaire_{self.file_name}"

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
            field_ids = [f.id for f in self.__fields]
            funcs = default_functions()

            def make_calc_method(calc_name, ast_node):
                referenced = referenced_fields(ast_node)

                def _calc(self):
                    env = {}
                    for fid in referenced:
                        if not hasattr(self, fid):
                            raise ExpressionError(
                                f"calculation {calc_name!r} on questionnaire "
                                f"{table_name!r} references unknown field {fid!r}"
                            )
                        raw = getattr(self, fid)
                        # Match the original eval-based behavior: numeric
                        # coercion via float() so int/None/numeric-string
                        # fields all participate in arithmetic uniformly.
                        try:
                            env[fid] = float(raw) if raw is not None else 0.0
                        except (TypeError, ValueError):
                            env[fid] = raw
                    try:
                        return expr_evaluate(ast_node, env, functions=funcs)
                    except Exception as e:
                        raise Exception(
                            f"Unable to evaluate calculated field "
                            f"`{calc_name}` on questionnaire `{table_name}`: {e}"
                        )

                return _calc

            for field_name, calculation in self.json_data["participant_calculations"].items():
                self.__calc_fields.append(field_name)
                try:
                    ast_node = parse_with_field_ids(calculation, field_ids)
                except ExpressionError as e:
                    raise Exception(
                        f"Unable to parse calculated field `{field_name}` on "
                        f"questionnaire `{table_name}`. Expression: "
                        f"`{calculation}`. {e}"
                    )
                table_attr[field_name] = make_calc_method(field_name, ast_node)

        # Detect orphaned columns and type mismatches by reflecting the existing DB table
        self._orphaned_columns = []
        self._type_mismatches = []
        try:
            inspector = sa_inspect(db.engine)
            if table_name in inspector.get_table_names():
                db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
                json_field_names = {field.id for field in self.__fields}

                for col_name, col_info in db_columns.items():
                    # Skip columns that are in the model (standard cols, fields, or calc properties)
                    if col_name in table_attr:
                        continue

                    # This column is in the DB but not in the model — it's orphaned
                    self._orphaned_columns.append(col_info)
                    table_attr[col_name] = db.Column(col_info['type'], nullable=True)

                # Check for type mismatches on fields present in both DB and JSON
                for field in self.__fields:
                    if field.id in db_columns:
                        db_col = db_columns[field.id]
                        if not _types_compatible(db_col['type'], field.data_type):
                            self._type_mismatches.append({
                                'field_id': field.id,
                                'db_type': _normalize_type_name(db_col['type']),
                                'json_type': field.data_type,
                            })
        except Exception:
            pass  # Skip if reflection fails (e.g., new database, table doesn't exist yet)

        self.db_class = type(self.file_name, (db.Model,), table_attr)

    def create_blank(self):
        blank = self.db_class()

        for column in blank.__table__.c:
            if column.default:
                setattr(blank, column.name, column.default.arg)
            if column.type == db.DateTime:
                setattr(blank, column.name, datetime.min)

        return blank

    def get_field(self, id):
        for f in self.__fields:
            if f.id == id:
                return f
        return None

    def fetch_all_data(self):
        return db.session.query(self.db_class).all()

    def fetch_finished_data(self):
        return db.session.query(self.db_class).join(db.Participant).filter(db.Participant.finished == True).all()

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
