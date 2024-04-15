import json
from functools import wraps
from flask import request, session, current_app, render_template, g, redirect, url_for
from BOFS.globals import db
import decimal, datetime
from sqlalchemy.engine import reflection


def _datetime_convert(v):
    return v.strftime("%Y-%m-%d %H:%M:%S")


def remove_non_ascii(s):
    return "".join([x for x in s if ord(x)<128]).encode('ascii', 'xmlcharrefreplace')


def alchemy_encoder(obj):
    """
    JSON encoder function for SQLAlchemy special classes.
    https://codeandlife.com/2014/12/07/sqlalchemy-results-to-json-the-easy-way/
    """
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, decimal.Decimal):
        return float(obj)


def sqlalchemy_to_json(inst, cls):
    """
    Jsonify the sqlalchemy query result.
    http://stackoverflow.com/questions/7102754/jsonify-a-sqlalchemy-result-set-in-flask
    """
    convert = dict()
    convert['DATETIME'] = _datetime_convert

    d = dict()
    for c in cls.columns:
        v = getattr(inst, c.name)
        if c.data_type in list(convert.keys()) and v is not None:
            try:
                d[c.name] = convert[c.data_type](v)
            except Exception:
                d[c.name] = "Error:  Failed to covert using ", str(convert[c.data_type])
        elif v is None:
            d[c.name] = str()
        else:
            if isinstance(v, str):
                d[c.name] = remove_non_ascii(v).replace("'", "&#39;").replace("{", "&#123;").replace("}", "&#125;")
            else:
                d[c.name] = str(v)
    return json.dumps(d)


def verify_admin(f):
    """
    A decorator to be used for admin routes, which checks if the user is logged in. If not, the login page is shown.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedIn' not in session or not session['loggedIn']:
            return redirect(url_for("admin.admin_login") + "?r=" + getattr(f, "__name__", str(f)))
        return f(*args, **kwargs)
    return decorated_function


def escape_csv(input):
    if isinstance(input, str):
        return str.format(u"\"{}\"", input.strip().replace("\n", " ").replace("\r", " ").replace("\"", "'"))
    if input is None:
        return str()
    if type(input) is bool:
        return str(1) if input == True else str(0)
    else:
        return str(input)


def condition_num_to_label(condition):
    if len(current_app.config['CONDITIONS']) == 0:
        return condition
    elif condition is None or condition == 0:
        return ""
    else:
        return current_app.config['CONDITIONS'][condition - 1]['label']


def questionnaire_name_and_tag(questionnnaireNameAndTagString):
    """
    The questionnaire paths might or might not include a tag, e.g., "questionnaire/tag".
    This function splits that up.
    :param questionnnaireNameAndTag:
    :return:
    """
    if u"/" in questionnnaireNameAndTagString:
        split = questionnnaireNameAndTagString.split(u"/")
        qName = split[0]
        qTag = split[1]
    else:
        qName = questionnnaireNameAndTagString
        qTag = ""

    return qName, qTag


def check_and_add_column(table_name: str, column_name: str, column_data_type: str, default_value) -> bool:
    """
    Check whether a table has been added to a particular table. Table name is not the class name, but the actual
    name of the table in the database. Only works for SQLite databases.

    :param table_name:
    :param column_name:
    :param column_data_type: in SQL DDL format, e.g., BOOLEAN, VARCHAR, TEXT, INTEGER etc.
    :param default_value: Must be at least a blank string
    :return:
    """
    is_sqlite = current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')

    if not is_sqlite:
        return False

    inspector = reflection.Inspector.from_engine(db.engine)
    inspector.get_columns(table_name)

    for column in inspector.get_columns(table_name):
        if column['name'] == column_name:
            return False # The column is already in the database

    add_column = db.DDL(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_data_type} DEFAULT {repr(default_value)}")
    with db.engine.connect() as conn:
        conn.execute(add_column)
        db.session.commit()

    return True

