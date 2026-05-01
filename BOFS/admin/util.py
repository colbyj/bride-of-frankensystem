import json
from functools import wraps
from flask import request, session, current_app, render_template, g, redirect, url_for
from BOFS.globals import db
import decimal, datetime
from sqlalchemy import inspect as sa_inspect


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

    When ``BRUTE_FORCE_PROTECTION`` is enabled, also checks that the
    request's client IP matches ``session['adminIp']`` (set at login).
    Mismatch clears the session and redirects to the login page so a
    stolen cookie can't be replayed from a different network.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedIn' not in session or not session['loggedIn']:
            return redirect(url_for("admin.admin_login") + "?r=" + getattr(f, "__name__", str(f)))

        if current_app.config.get('BRUTE_FORCE_PROTECTION', True):
            from BOFS.services import brute_force
            current_ip = brute_force.get_client_ip()
            stored_ip = session.get('adminIp')
            if stored_ip != current_ip:
                session.pop('loggedIn', None)
                session.pop('adminIp', None)
                session.modified = True
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


def check_and_add_column(table_name: str, column_name: str, column_data_type: str, default_value=None) -> bool:
    """
    Check whether a column exists in a table; if not, add it. Table name is the actual
    name of the table in the database, not the class name. Only works for SQLite databases.

    :param table_name:
    :param column_name:
    :param column_data_type: in SQL DDL format, e.g., BOOLEAN, VARCHAR, TEXT, INTEGER etc.
    :param default_value: If provided, the column is added with NOT NULL DEFAULT <value>.
        If None (default), the column is added as nullable with no default.
    :return: True if the column was added, False if it already existed.
    """
    is_sqlite = current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')

    if not is_sqlite:
        return False

    inspector = sa_inspect(db.engine)

    for column in inspector.get_columns(table_name):
        if column['name'] == column_name:
            return False # The column is already in the database

    if default_value is not None:
        ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_data_type} DEFAULT {repr(default_value)}"
    else:
        ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_data_type}"

    add_column = db.DDL(ddl)
    with db.engine.connect() as conn:
        conn.execute(add_column)
        db.session.commit()

    return True


def make_columns_nullable(table_name: str, column_names: list) -> bool:
    """
    Make specified columns nullable in a SQLite table via table reconstruction.

    SQLite does not support ALTER TABLE ALTER COLUMN, so the standard approach is to
    rebuild the table with a modified schema. This preserves all existing data.

    Only works for SQLite databases.

    :param table_name: The actual table name in the database.
    :param column_names: List of column names to make nullable.
    :return: True if the table was rebuilt, False if no changes were needed.
    """
    if not column_names:
        return False

    is_sqlite = current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')
    if not is_sqlite:
        return False

    inspector = sa_inspect(db.engine)

    if table_name not in inspector.get_table_names():
        return False

    columns = inspector.get_columns(table_name)
    pk_constraint = inspector.get_pk_constraint(table_name)
    fks = inspector.get_foreign_keys(table_name)
    indexes = inspector.get_indexes(table_name)

    pk_columns = pk_constraint.get('constrained_columns') or []

    # Check if any target columns actually need changing (are currently NOT NULL)
    columns_to_change = set()
    for col in columns:
        if col['name'] in column_names and not col['nullable']:
            columns_to_change.add(col['name'])

    if not columns_to_change:
        return False  # All target columns are already nullable

    # Build column definitions for the new table
    col_defs = []
    for col in columns:
        name = col['name']
        type_str = str(col['type'])
        parts = [f'"{name}"', type_str]

        # Primary key
        if name in pk_columns:
            parts.append('PRIMARY KEY')
            # INTEGER PRIMARY KEY implies AUTOINCREMENT in SQLite
            if type_str.upper() == 'INTEGER' and col.get('autoincrement', False):
                parts.append('AUTOINCREMENT')

        # NOT NULL — skip for columns we're making nullable
        if not col['nullable'] and name not in columns_to_change:
            parts.append('NOT NULL')

        # Default
        if col['default'] is not None:
            parts.append(f"DEFAULT {col['default']}")

        col_defs.append(' '.join(parts))

    # Foreign key constraints
    for fk in fks:
        for i in range(len(fk['constrained_columns'])):
            col_defs.append(
                f'FOREIGN KEY("{fk["constrained_columns"][i]}") '
                f'REFERENCES "{fk["referred_table"]}"("{fk["referred_columns"][i]}")'
            )

    col_names_str = ', '.join(f'"{col["name"]}"' for col in columns)
    backup_name = f"{table_name}__rebuild_backup"

    new_create = f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})'

    from sqlalchemy import text
    with db.engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{backup_name}"'))
        conn.execute(text(new_create))
        conn.execute(text(
            f'INSERT INTO "{table_name}" ({col_names_str}) '
            f'SELECT {col_names_str} FROM "{backup_name}"'
        ))
        conn.execute(text(f'DROP TABLE "{backup_name}"'))

        # Recreate indexes
        for idx in indexes:
            idx_cols = ', '.join(f'"{c}"' for c in idx['column_names'])
            unique = 'UNIQUE ' if idx.get('unique') else ''
            conn.execute(text(
                f'CREATE {unique}INDEX "{idx["name"]}" ON "{table_name}" ({idx_cols})'
            ))

        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()

    changed_names = ', '.join(sorted(columns_to_change))
    print(f"  Made column(s) nullable in {table_name}: {changed_names}")
    return True

