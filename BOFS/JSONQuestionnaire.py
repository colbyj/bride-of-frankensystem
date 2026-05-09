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


# Per-question-type schemas for fields that live on nested items rather
# than the question dict itself. The docstring schemas only describe
# top-level question attributes; researcher-typed values inside lists
# (e.g. checklist items) live here. Keep this list short — only fields
# whose intended type is unambiguous belong here. Fields whose type is
# intentionally polymorphic (picture_select image ``value``) are absent
# on purpose so coercion doesn't change their type.
_NESTED_ITEM_TYPES: dict = {
    # checklist sub-items: parent's ``questions`` array
    "checklist": {
        "container": "questions",
        "fields": {
            "text_entry": "bool",
            "text_entry_hides": "bool",
            "text_entry_width": "int",
        },
    },
}


def _coerce_int(value, file_name: str, key_path: str):
    # bool is a subclass of int — leave booleans alone so a stray ``true``
    # in a numeric slot surfaces via validation instead of silently
    # turning into 1.
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise SyntaxError(
            "ERROR! Questionnaire `%s` field `%s` expects an integer, "
            "got %r." % (file_name, key_path, value)
        )
    if isinstance(value, str):
        s = value.strip()
        if s != "":
            try:
                return int(s)
            except ValueError:
                try:
                    f = float(s)
                except ValueError:
                    pass
                else:
                    if f.is_integer():
                        return int(f)
        raise SyntaxError(
            "ERROR! Questionnaire `%s` field `%s` expects an integer, "
            "got %r." % (file_name, key_path, value)
        )
    return value


def _coerce_float(value, file_name: str, key_path: str):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s != "":
            try:
                return float(s)
            except ValueError:
                pass
        raise SyntaxError(
            "ERROR! Questionnaire `%s` field `%s` expects a number, "
            "got %r." % (file_name, key_path, value)
        )
    return value


def _coerce_bool(value, file_name: str, key_path: str):
    # Mirrors the accepted-string set used by ``BOFS.JSONTable._coerce_bool``
    # for participant POST data, so researchers see consistent truthy/falsy
    # rules across the framework.
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        raise SyntaxError(
            "ERROR! Questionnaire `%s` field `%s` expects a boolean "
            "(true/false), got %r." % (file_name, key_path, value)
        )
    return value


def _coerce_value(value, type_name: str, file_name: str, key_path: str):
    type_name = (type_name or "").strip().lower().split(",")[0].strip()
    if type_name in ("int", "integer"):
        return _coerce_int(value, file_name, key_path)
    if type_name in ("float", "number"):
        return _coerce_float(value, file_name, key_path)
    if type_name in ("bool", "boolean"):
        return _coerce_bool(value, file_name, key_path)
    return value


def _coerce_question(q: dict, file_name: str, key_path: str) -> None:
    """Coerce string-encoded numbers/bools to their declared types on a
    single question dict, then descend into group sub-questions and nested
    items for which we know the per-field types."""
    from . import question_schemas  # local import to avoid a startup cycle

    if not isinstance(q, dict):
        return
    qtype = q.get("questiontype")
    if not isinstance(qtype, str):
        return

    schema = question_schemas.get_schema(qtype)
    if schema is not None:
        for attr in schema.attributes:
            if attr.name in q:
                q[attr.name] = _coerce_value(
                    q[attr.name], attr.type, file_name,
                    f"{key_path}.{attr.name}",
                )

    # Group sub-questions follow their own type's schema.
    if qtype == "group":
        for j, sub in enumerate(q.get("questions") or []):
            _coerce_question(sub, file_name, f"{key_path}.questions[{j}]")

    # Per-type nested-item fields (e.g. checklist row text_entry flags).
    nested = _NESTED_ITEM_TYPES.get(qtype)
    if nested:
        for j, item in enumerate(q.get(nested["container"]) or []):
            if not isinstance(item, dict):
                continue
            for field_name, field_type in nested["fields"].items():
                if field_name in item:
                    item[field_name] = _coerce_value(
                        item[field_name], field_type, file_name,
                        f"{key_path}.{nested['container']}[{j}]"
                        f".{field_name}",
                    )


def _coerce_questionnaire_types(json_data, file_name: str) -> None:
    """Walk a parsed questionnaire and coerce numeric/boolean fields whose
    declared schema type is int/float/bool but whose JSON value arrived as
    a string. The questionnaire JSON file format is hand-edited, so loose
    values like ``"true"`` or ``"5"`` are common; coercing once at load
    time means no downstream consumer (templates, validation, the page
    renderer) has to be type-tolerant."""
    if not isinstance(json_data, dict):
        return
    questions = json_data.get("questions")
    if not isinstance(questions, list):
        return
    for i, q in enumerate(questions):
        _coerce_question(q, file_name, f"questions[{i}]")


def _normalize_question_type_keys(node, file_name: str) -> None:
    """Walk a parsed questionnaire structure in-place and rename the
    ``question_type`` alias to the canonical ``questiontype`` key.

    Researchers may write either form; everything downstream (validation,
    column emission, templates, expression substitution) reads
    ``questiontype``, so the alias is collapsed once at load time. If both
    keys are present on the same dict, equal values are tolerated and the
    alias is dropped; differing values raise a SyntaxError because the
    intent is ambiguous.
    """
    if isinstance(node, dict):
        if 'question_type' in node:
            alias_value = node['question_type']
            if 'questiontype' in node:
                if node['questiontype'] != alias_value:
                    raise SyntaxError(
                        "ERROR! Questionnaire `%s` has both `questiontype` "
                        "and `question_type` set to different values "
                        "(%r vs %r). Use one." %
                        (file_name, node['questiontype'], alias_value)
                    )
            else:
                node['questiontype'] = alias_value
            del node['question_type']
        for value in node.values():
            _normalize_question_type_keys(value, file_name)
    elif isinstance(node, list):
        for item in node:
            _normalize_question_type_keys(item, file_name)


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
        self.nullable = False

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

        # Radiogrid row columns are nullable so the optional N/A column can
        # store the row's value as NULL. Researchers who never enable
        # ``na_column`` see no behavioural difference: regular selections
        # still write a non-null string.
        if question_type.lower() == "radiogrid":
            self.nullable = True
            self.default = None

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
            return db.Column(db.Integer, nullable=self.nullable, default=self.default)
        elif self.data_type == "float":
            return db.Column(db.Float, nullable=self.nullable, default=self.default)
        elif self.data_type == "datetime":
            return db.Column(db.DateTime, nullable=self.nullable, default=self.default)
        elif self.data_type == "boolean":
            return db.Column(db.Boolean, nullable=self.nullable, default=self.default)
        else:
            return db.Column(db.Text, nullable=self.nullable, default=self.default)


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

        # Collapse the ``question_type`` alias to the canonical
        # ``questiontype`` before any downstream code reads it.
        _normalize_question_type_keys(self.json_data, file_name)

        # Coerce string-encoded numbers and booleans to their declared
        # types (so ``"5"``, ``"true"``, ``"FALSE"`` work in hand-edited
        # JSON). Runs after the alias collapse so schema lookups can use
        # the canonical questiontype.
        _coerce_questionnaire_types(self.json_data, file_name)

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

    def _collect_label_stored_row_ids(self) -> set:
        """Return the set of row ids that belong to a radiogrid with
        ``store_labels: true``. These rows hold label strings, so calc
        fields can't coerce them to numbers; ``create_db_class`` uses this
        to reject calcs that reference them."""
        ids: set = set()

        def _scan(question_list):
            for q in question_list or []:
                if not isinstance(q, dict):
                    continue
                if q.get('questiontype') == 'group':
                    _scan(q.get('questions') or [])
                    continue
                if q.get('questiontype') != 'radiogrid' or not q.get('store_labels'):
                    continue
                rows = q.get('q_text') or q.get('questions') or []
                for row in rows:
                    if isinstance(row, dict) and 'id' in row:
                        ids.add(row['id'])

        if isinstance(self.json_data, dict):
            _scan(self.json_data.get('questions') or [])
        return ids

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

            if q.get('questiontype') == 'group':
                # Heterogeneous container: each sub-question contributes its
                # own column(s) under its own questiontype. The group's own
                # id is never a column. ``textview`` subs are allowed (for
                # mid-group prose) and naturally produce no columns since
                # they have no id; nested groups are rejected at validation.
                for sub in q.get('questions', []):
                    if sub.get('questiontype') == 'group':
                        continue  # validation rejects this; defence in depth
                    if 'q_text' in sub and 'questions' not in sub:
                        sub['questions'] = sub['q_text']
                    self._emit_question_columns(sub, self.__fields)
                continue

            self._emit_question_columns(q, self.__fields)

        return self.__fields

    @staticmethod
    def _emit_question_columns(q: dict, fields: list) -> None:
        """Append column(s) for a single question definition.

        Handles all column-emission cases used by both top-level questions
        and group sub-questions:
          * Homogeneous nested types (radiogrid/checklist): each row id
            becomes a column whose data_type derives from the parent's
            questiontype.
          * ``image_click`` (single vs multi-click branches).
          * ``EXPANDED_TYPES`` fanout (audio/video).
          * Generic 1:1 case.

        Container questions (those with a non-empty nested ``questions``
        list) emit columns only for their rows — the parent id is structural
        and never a column."""
        qtype = q.get('questiontype')

        # Homogeneous nested rows (radiogrid, checklist) — container case.
        # The parent's own id is not a DB column; only the row ids are.
        if q.get('questions'):
            for row in q['questions']:
                if 'id' in row:
                    fields.append(JSONQuestionnaireColumn(row, qtype))
            return

        if 'id' not in q:
            return

        if qtype == 'image_click':
            # Single-click (max_clicks omitted or == 1) stores natural-image
            # pixel x,y as two float columns. Multi-click stores a JSON
            # array of {"x":..,"y":..} points in one TEXT column.
            max_clicks = q.get('max_clicks', 1)
            if isinstance(max_clicks, int) and max_clicks == 1:
                for suffix in ('_x', '_y'):
                    fields.append(JSONQuestionnaireColumn(
                        {'id': q['id'] + suffix, 'datatype': 'float'}))
            else:
                fields.append(JSONQuestionnaireColumn(
                    {'id': q['id'], 'datatype': 'string'}))
        elif qtype in EXPANDED_TYPES:
            for suffix, dtype in EXPANDED_TYPES[qtype]:
                fields.append(JSONQuestionnaireColumn(
                    {'id': q['id'] + suffix, 'datatype': dtype}))
        else:
            fields.append(JSONQuestionnaireColumn(q))

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
            label_stored_row_ids = self._collect_label_stored_row_ids()

            def make_calc_method(calc_name, ast_node):
                referenced = referenced_fields(ast_node)

                def _calc(self):
                    # Build the evaluation env. Missing values (None or empty
                    # string — e.g. a radiogrid item with no option selected)
                    # become None so the evaluator can propagate them: a calc
                    # that depends on a missing field returns None for that
                    # row rather than crashing the whole export.
                    env = {}
                    for fid in referenced:
                        if not hasattr(self, fid):
                            raise ExpressionError(
                                f"calculation {calc_name!r} on questionnaire "
                                f"{table_name!r} references unknown field {fid!r}"
                            )
                        raw = getattr(self, fid)
                        if raw is None or raw == "":
                            env[fid] = None
                        else:
                            try:
                                env[fid] = float(raw)
                            except (TypeError, ValueError):
                                env[fid] = raw
                    try:
                        return expr_evaluate(ast_node, env, functions=funcs)
                    except Exception as e:
                        ref_state = ", ".join(
                            f"{k}={env.get(k)!r}" for k in referenced
                        )
                        raise Exception(
                            f"Unable to evaluate calculated field "
                            f"`{calc_name}` on questionnaire `{table_name}`: "
                            f"{e}. Referenced fields: {ref_state}"
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
                # Calc fields coerce referenced values to float; rows from
                # ``store_labels: true`` grids hold label strings that can't
                # be coerced, so reject the configuration up front instead
                # of producing a calc that always errors at row time.
                offending = sorted(set(referenced_fields(ast_node)) & label_stored_row_ids)
                if offending:
                    raise Exception(
                        f"Calculated field `{field_name}` on questionnaire "
                        f"`{table_name}` references row(s) "
                        f"{', '.join(repr(r) for r in offending)} from a "
                        f"radiogrid with `store_labels: true`. Calc fields "
                        f"require numeric (index) storage; remove "
                        f"`store_labels` from that grid or drop the "
                        f"reference from the calc."
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
