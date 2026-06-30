import csv
import io
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
                # An IP mismatch on a logged-in admin session is exactly
                # the kind of signal worth keeping — it can mean a stolen
                # cookie used from another network, a roaming admin, or a
                # mid-session reverse-proxy reconfig. Log it so it's
                # visible in the access log alongside the silent redirect.
                current_app.logger.warning(
                    "verify_admin: admin session cleared on IP mismatch "
                    "(stored=%s current=%s endpoint=%s)",
                    stored_ip, current_ip, getattr(f, "__name__", str(f)),
                )
                session.pop('loggedIn', None)
                session.pop('adminIp', None)
                session.modified = True
                return redirect(url_for("admin.admin_login") + "?r=" + getattr(f, "__name__", str(f)))

        return f(*args, **kwargs)
    return decorated_function


_FORMULA_SIGILS = ('=', '+', '-', '@', '\t')


def formula_safe(value):
    """Return *value* with a single-quote prefix when it begins with a CSV
    formula sigil (``=``, ``+``, ``-``, ``@``, or tab). Spreadsheet apps treat
    those leading characters as the start of a formula; the prefix neutralises
    that without altering the visible value (the leading ``'`` is consumed on
    display). Non-string values pass through unchanged so numeric / boolean
    cells aren't coerced to strings unnecessarily."""
    if isinstance(value, str) and value and value[0] in _FORMULA_SIGILS:
        return "'" + value
    return value


def _csv_cell(value):
    """Coerce *value* to the form ``csv.writer`` should receive.

    csv.writer stringifies non-string scalars itself, but BOFS exports
    historically rendered ``True``/``False`` as ``1``/``0`` and ``None`` as the
    empty string. Preserve those conventions so existing exports stay readable.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return formula_safe(value)


def csv_string(rows) -> str:
    """Render *rows* as RFC 4180 CSV. Each row is an iterable of cells; each
    cell is coerced via ``_csv_cell`` (formula-injection safe, ``None`` → "",
    bool → ``1``/``0``)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    for row in rows:
        writer.writerow([_csv_cell(c) for c in row])
    return buf.getvalue()


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


_SUPPORTED_MIGRATION_DIALECTS = ('sqlite', 'postgresql', 'mysql', 'mariadb')


def _engine_for(bind_key):
    """Resolve a SQLAlchemy Engine for *bind_key*. ``None`` -> default engine.

    Raises ``ValueError`` with the configured bind names when *bind_key* is
    not in ``SQLALCHEMY_BINDS`` — clearer than the bare ``KeyError`` that
    ``db.engines[bind_key]`` would otherwise produce. Reachable only when
    validation was bypassed (e.g. constructing ``JSONQuestionnaire``
    directly in tests or custom code without going through the normal
    ``load_questionnaire`` path).
    """
    if bind_key is None:
        return db.engine
    try:
        return db.engines[bind_key]
    except KeyError:
        configured = sorted(k for k in db.engines if k is not None)
        raise ValueError(
            f"Unknown bind {bind_key!r}. Configured binds in SQLALCHEMY_BINDS: "
            f"{configured or '(none)'}."
        )


def _check_migration_dialect_supported(operation: str, bind_key=None) -> bool:
    """Return True if the target bind's DB dialect supports our migration helpers.

    Logs a clear warning (once per call) when it doesn't, so a Postgres/MySQL
    admin on an unsupported dialect can run the ALTER manually instead of
    silently ending up with a schema/ORM mismatch.
    """
    dialect = _engine_for(bind_key).dialect.name
    if dialect in _SUPPORTED_MIGRATION_DIALECTS:
        return True
    current_app.logger.warning(
        "%s skipped: dialect %r on bind %r is not in the supported list %r. "
        "Run the equivalent ALTER TABLE statement manually.",
        operation, dialect, bind_key, _SUPPORTED_MIGRATION_DIALECTS,
    )
    return False


def check_and_add_column(table_name: str, column_name: str, column_data_type: str, default_value=None, bind_key=None) -> bool:
    """
    Check whether a column exists in a table; if not, add it. Table name is the actual
    name of the table in the database, not the class name.

    Works on SQLite, PostgreSQL, MySQL/MariaDB — all four accept the same
    ``ALTER TABLE ... ADD COLUMN`` syntax for the simple cases BOFS uses. Other
    dialects are skipped with a warning so an admin can run the ALTER manually.

    :param table_name:
    :param column_name:
    :param column_data_type: in SQL DDL format, e.g., BOOLEAN, VARCHAR, TEXT, INTEGER etc.
    :param default_value: If provided, the column is added with NOT NULL DEFAULT <value>.
        If None (default), the column is added as nullable with no default.
    :param bind_key: Name of a SQLALCHEMY_BINDS entry. ``None`` (default) targets
        the default-bind engine. Pass the bind key for a cross-bind questionnaire
        or table so the inspector and DDL run against the correct engine.
    :return: True if the column was added, False if it already existed (or was skipped).
    """
    if not _check_migration_dialect_supported(
        f"check_and_add_column({table_name!r}, {column_name!r})",
        bind_key=bind_key,
    ):
        return False

    engine = _engine_for(bind_key)
    inspector = sa_inspect(engine)

    for column in inspector.get_columns(table_name):
        if column['name'] == column_name:
            return False # The column is already in the database

    if default_value is not None:
        ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_data_type} DEFAULT {repr(default_value)}"
    else:
        ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_data_type}"

    add_column = db.DDL(ddl)
    with engine.connect() as conn:
        conn.execute(add_column)
        db.session.commit()

    return True


def check_and_rename_column(table_name: str, old_name: str, new_name: str, bind_key=None) -> bool:
    """Rename a column if the old name exists and the new name does not.

    Works on SQLite >= 3.25, PostgreSQL >= 9.2, MySQL >= 8.0, MariaDB >= 10.5 —
    all accept the identical ``ALTER TABLE ... RENAME COLUMN ... TO ...`` syntax.
    Older versions of Postgres/MySQL are out of support; the ALTER will raise
    and surface the version mismatch clearly. Other dialects are skipped with
    a warning so an admin can run the rename manually.

    Backward-compatibility note: this helper exists because BOFS treats
    pre-existing study databases as part of the public contract (see CLAUDE.md
    "Backward Compatibility"). A SQLite-only rename would silently leave
    Postgres/MySQL deployments with the old column while the ORM expected the
    new one — every read/write would then raise.

    :param bind_key: Name of a SQLALCHEMY_BINDS entry. ``None`` (default) targets
        the default-bind engine.
    :return: True if the rename happened, False if it was a no-op (already
        renamed) or skipped (unsupported dialect).
    """
    if not _check_migration_dialect_supported(
        f"check_and_rename_column({table_name!r}, {old_name!r} -> {new_name!r})",
        bind_key=bind_key,
    ):
        return False

    engine = _engine_for(bind_key)
    inspector = sa_inspect(engine)
    existing = {col['name'] for col in inspector.get_columns(table_name)}

    if new_name in existing:
        return False  # already renamed (or new schema all along)
    if old_name not in existing:
        return False  # nothing to rename

    ddl = f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}"
    with engine.connect() as conn:
        conn.execute(db.DDL(ddl))
        db.session.commit()

    return True


def check_and_rename_table(old_name: str, new_name: str, bind_key=None) -> bool:
    """Rename a table if the old name exists and the new name does not.

    Works on SQLite >= 3.25, PostgreSQL >= 9.2, MySQL >= 8.0, MariaDB >= 10.5 —
    all accept the identical ``ALTER TABLE ... RENAME TO ...`` syntax.
    Older versions of Postgres/MySQL are out of support; the ALTER will raise
    and surface the version mismatch clearly. Other dialects are skipped with
    a warning so an admin can run the rename manually.

    Backward-compatibility note: this helper exists because BOFS treats
    pre-existing study databases as part of the public contract (see CLAUDE.md
    "Backward Compatibility"). A framework table that was renamed (e.g.
    ``questionnaire_interaction`` to ``bofs_interaction_log``) must be
    migrated in place so existing deployments retain their data.

    :param bind_key: Name of a SQLALCHEMY_BINDS entry. ``None`` (default) targets
        the default-bind engine.
    :return: True if the rename happened, False if it was a no-op (already
        renamed, nothing to rename) or skipped (unsupported dialect).
    """
    if not _check_migration_dialect_supported(
        f"check_and_rename_table({old_name!r} -> {new_name!r})",
        bind_key=bind_key,
    ):
        return False

    engine = _engine_for(bind_key)
    inspector = sa_inspect(engine)
    existing = set(inspector.get_table_names())

    if new_name in existing:
        return False  # already renamed (or new schema all along)
    if old_name not in existing:
        return False  # nothing to rename

    ddl = f"ALTER TABLE {old_name} RENAME TO {new_name}"
    with engine.connect() as conn:
        conn.execute(db.DDL(ddl))
        db.session.commit()

    return True


def make_columns_nullable(table_name: str, column_names: list, bind_key=None) -> bool:
    """
    Make specified columns nullable in a SQLite table via table reconstruction.

    SQLite does not support ALTER TABLE ALTER COLUMN, so the standard approach is to
    rebuild the table with a modified schema. This preserves all existing data.

    Only works for SQLite databases.

    :param table_name: The actual table name in the database.
    :param column_names: List of column names to make nullable.
    :param bind_key: Name of a SQLALCHEMY_BINDS entry. ``None`` (default) targets
        the default-bind engine.
    :return: True if the table was rebuilt, False if no changes were needed.
    """
    if not column_names:
        return False

    engine = _engine_for(bind_key)
    if engine.dialect.name != 'sqlite':
        return False

    inspector = sa_inspect(engine)

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
    with engine.connect() as conn:
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


def add_progress_occurrence_column(bind_key=None) -> bool:
    """Add the ``occurrence`` column to the ``progress`` table and recompose
    its primary key to ``(participantID, path, occurrence)``.

    Idempotent: no-op when ``occurrence`` already exists. Existing rows
    backfill to ``occurrence = 0`` — safe because no existing study could
    have had two Progress rows for one ``(participantID, path)`` pair.

    On SQLite the table is rebuilt (SQLite cannot alter a primary key in
    place); on PostgreSQL/MySQL/MariaDB the column is added with
    ``ALTER TABLE`` and the PK constraint is dropped and recreated.

    :param bind_key: Name of a SQLALCHEMY_BINDS entry. ``None`` (default)
        targets the default-bind engine.
    :return: True if the migration ran, False if it was a no-op (already
        migrated, table missing, or unsupported dialect).
    """
    if not _check_migration_dialect_supported(
        "add_progress_occurrence_column", bind_key=bind_key,
    ):
        return False

    engine = _engine_for(bind_key)
    inspector = sa_inspect(engine)

    if 'progress' not in inspector.get_table_names():
        return False

    existing_cols = {col['name'] for col in inspector.get_columns('progress')}
    if 'occurrence' in existing_cols:
        return False

    dialect = engine.dialect.name
    from sqlalchemy import text

    if dialect == 'sqlite':
        _rebuild_progress_table_sqlite(engine, inspector)
    else:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE progress ADD COLUMN occurrence INTEGER NOT NULL DEFAULT 0"
            ))
            pk_constraint = inspector.get_pk_constraint('progress')
            pk_name = pk_constraint.get('name')
            if pk_name and dialect == 'postgresql':
                conn.execute(text(
                    f"ALTER TABLE progress DROP CONSTRAINT {pk_name}"
                ))
            else:
                conn.execute(text("ALTER TABLE progress DROP PRIMARY KEY"))
            conn.execute(text(
                "ALTER TABLE progress ADD PRIMARY KEY (participantID, path, occurrence)"
            ))
            conn.commit()

    print("  Added 'occurrence' column to progress table and recomposed PK.")
    return True


def _rebuild_progress_table_sqlite(engine, inspector):
    """Rebuild the ``progress`` table on SQLite to add ``occurrence`` and
    recompose the primary key.

    Follows the same rename → create → copy → drop → reindex pattern as
    :func:`make_columns_nullable`.
    """
    from sqlalchemy import text

    columns = inspector.get_columns('progress')
    fks = inspector.get_foreign_keys('progress')
    indexes = inspector.get_indexes('progress')

    new_pk_cols = ['participantID', 'path', 'occurrence']

    col_defs = []
    old_col_names = []
    for col in columns:
        name = col['name']
        type_str = str(col['type'])
        parts = [f'"{name}"', type_str]

        if not col['nullable']:
            parts.append('NOT NULL')

        col_defs.append(' '.join(parts))
        old_col_names.append(f'"{name}"')

    col_defs.append('"occurrence" INTEGER NOT NULL DEFAULT 0')
    old_col_names_with_occ = old_col_names + ['"occurrence"']

    for fk in fks:
        for i in range(len(fk['constrained_columns'])):
            col_defs.append(
                f'FOREIGN KEY("{fk["constrained_columns"][i]}") '
                f'REFERENCES "{fk["referred_table"]}"("{fk["referred_columns"][i]}")'
            )

    pk_col_str = ', '.join(f'"{c}"' for c in new_pk_cols)
    col_defs.append(f'PRIMARY KEY ({pk_col_str})')

    all_col_names = ', '.join(old_col_names_with_occ)
    backup_name = "progress__rebuild_backup"
    new_create = f'CREATE TABLE "progress" ({", ".join(col_defs)})'

    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text(f'ALTER TABLE "progress" RENAME TO "{backup_name}"'))
        conn.execute(text(new_create))
        conn.execute(text(
            f'INSERT INTO "progress" ({all_col_names}) '
            f'SELECT {", ".join(old_col_names)}, 0 FROM "{backup_name}"'
        ))
        conn.execute(text(f'DROP TABLE "{backup_name}"'))

        for idx in indexes:
            idx_cols = ', '.join(f'"{c}"' for c in idx['column_names'])
            unique = 'UNIQUE ' if idx.get('unique') else ''
            conn.execute(text(
                f'CREATE {unique}INDEX "{idx["name"]}" ON "progress" ({idx_cols})'
            ))

        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()

