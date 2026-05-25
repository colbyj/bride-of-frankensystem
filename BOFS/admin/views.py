import hmac
import os
import re
from flask import Blueprint, render_template, current_app, redirect, g, request, session, url_for, Response, send_file, abort
from flask_wtf.csrf import generate_csrf, validate_csrf
from werkzeug.routing import BuildError
from wtforms.validators import ValidationError
from .. import BOFSFlask
from ..globals import db, questionnaires, page_list
from ..util import fetch_condition_count, display_time, provide_consent, int_or_0, utcnow_naive
from .util import sqlalchemy_to_json, verify_admin, formula_safe, csv_string, questionnaire_name_and_tag, condition_num_to_label
from ..services.participant_questionnaire import ParticipantQuestionnaireService
from ..services.data_export import Results
import json
from ..services.admin_stats import AdminStatsService
from ..services.participant import ParticipantService
from datetime import datetime
from os import path, listdir
from shutil import copyfile


current_app: "BOFSFlask"
admin = Blueprint('admin', __name__, template_folder='templates', static_folder='static', url_prefix="/admin")


_CSRF_PROTECTED_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# ``?r=`` on /admin/login is only ever set by verify_admin, which passes the
# wrapped view's ``__name__`` (a Python identifier). Restricting r to the
# identifier shape blocks attempts to smuggle URL syntax or path traversal
# through ``url_for("admin." + r)`` even before werkzeug's BuildError check.
_REDIRECT_ENDPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# Tables that hold framework state and must not be surfaced through the
# generic table viewer. ``app_meta`` carries the SECRET_KEY (deliberately
# moved out of config.toml so it wouldn't sit in researcher backups);
# exposing it in the admin UI would defeat that.
_TABLE_VIEW_BLOCKED = frozenset({'app_meta'})

# Framework-defined default-bind tables that get their own "System Data"
# submenu in the navbar Database dropdown. Everything *else* on the
# default bind is treated as researcher-defined and listed separately.
# These tables are defined in ``BOFS/default/models.py``.
_SYSTEM_TABLE_NAMES = frozenset({
    'participant', 'progress', 'display', 'banned_ip',
    'admin_trusted_ip', 'login_attempt', 'questionnaire_interaction',
    'response_log', 'session_store',
})


_NO_STORE_PATH_PREFIXES = (
    '/admin/export',
    '/admin/results',
    '/admin/table_view',
    '/admin/table_ajax',
    '/admin/table_csv',
    '/admin/database_download',
    '/admin/export_item_timing',
)


@admin.after_request
def _admin_no_store(response):
    """Tell browsers and intermediate proxies not to cache responses that
    carry participant data — exports, the SQLite download, table dumps.
    Without this, a researcher viewing the export then walking away from
    their machine leaves the rendered data sitting in the browser cache."""
    path = request.path or ''
    if any(path.startswith(p) for p in _NO_STORE_PATH_PREFIXES):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
    return response


@admin.before_request
def _verify_admin_csrf():
    """Block cross-site state-changing requests against the admin blueprint.

    Reads the token from the standard Flask-WTF locations (``csrf_token``
    form field or ``X-CSRFToken`` / ``X-CSRF-Token`` header). Participant
    blueprints are not affected — the check is scoped to ``/admin/*`` via
    the blueprint hook. Honors ``WTF_CSRF_ENABLED`` so test suites can
    disable the check without exercising token plumbing."""
    if not current_app.config.get('WTF_CSRF_ENABLED', True):
        return
    if request.method not in _CSRF_PROTECTED_METHODS:
        return
    token = (
        request.form.get('csrf_token')
        or request.headers.get('X-CSRFToken')
        or request.headers.get('X-CSRF-Token')
    )
    try:
        validate_csrf(token)
    except ValidationError:
        abort(403, description="CSRF token missing or invalid.")


@admin.context_processor
def inject_template_vars():
    """
    Inject additional variables into the context of templates within this blueprint
    See http://flask.pocoo.org/docs/1.0/templating/#context-processors
    :return:
    """

    if "ADDITIONAL_ADMIN_PAGES" in current_app.config:
        additionalAdminPages = current_app.config['ADDITIONAL_ADMIN_PAGES']
    else:
        additionalAdminPages = None

    # Categorise tables for the Database dropdown:
    #   - system_tables: framework default-bind tables (Participant,
    #     Progress, etc.) — researchers occasionally need to inspect these
    #     but the list is fixed.
    #   - user_tables: default-bind tables defined by the researcher
    #     (questionnaire_*, table_*, blueprint models).
    #   - bind_tables: dict keyed by bind name → list of table names on
    #     that engine. Surfaced as one submenu per configured bind so the
    #     dropdown reflects the actual storage layout, not a flat union.
    #
    # Flask-SQLAlchemy 3.x keeps a separate MetaData per bind (``db.metadatas``,
    # keyed by bind name with ``None`` for the default bind). Cross-bind
    # tables don't appear in ``db.metadata.tables``, so we have to walk
    # every MetaData explicitly.
    system_tables = []
    user_tables = []
    bind_tables = {}

    for bk, md in db.metadatas.items():
        for t_name in md.tables:
            if t_name in _TABLE_VIEW_BLOCKED:
                continue
            if bk is None:
                if t_name in _SYSTEM_TABLE_NAMES:
                    system_tables.append(t_name)
                else:
                    user_tables.append(t_name)
            else:
                bind_tables.setdefault(bk, []).append(t_name)

    system_tables.sort()
    user_tables.sort()
    for bk in bind_tables:
        bind_tables[bk].sort()

    # Legacy flat list, still passed for any external template override
    # that expects ``tableNames``. The new dropdown structure uses the
    # categorised lists above.
    tableNames = sorted(system_tables + user_tables + [
        name for names in bind_tables.values() for name in names
    ])

    questionnairesSystem = []
    questionnairesLive = []

    for q_name in current_app.questionnaires:
        questionnairesSystem.append(q_name)

        if current_app.questionnaires[q_name].is_in_db:
            questionnairesLive.append(q_name)

    questionnairesLive.sort()
    questionnairesSystem.sort()
    isSqliteDb = current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')

    # Per-bind navbar export menu: one entry per configured bind that
    # actually has a column-owning questionnaire/table loaded. The
    # default-bind entry ("Main Database") is always present.
    configured_binds = current_app.config.get('SQLALCHEMY_BINDS', {}) or {}
    used_binds_in_export = sorted(bind_tables.keys() & set(configured_binds))

    return dict(
        additionalAdminPages=additionalAdminPages,
        tableNames=tableNames,
        systemTables=system_tables,
        userTables=user_tables,
        bindTables=bind_tables,
        questionnairesLive=questionnairesLive,
        questionnairesSystem=questionnairesSystem,
        logInteractions=current_app.config['LOG_QUESTIONNAIRE_INTERACTIONS'],
        isSqliteDb=isSqliteDb,
        exportBinds=used_binds_in_export,
        condition_num_to_label=condition_num_to_label,
        csrf_token=generate_csrf,
    )


@admin.route("/")
def admin_index():
    return redirect(url_for("admin.admin_login"))


@admin.route("/logout", methods=['POST'])
@verify_admin
def admin_logout():
    """Fully log the admin out. POST-only (CSRF-protected by the blueprint
    before_request hook). Clears the session dict, deletes the SessionStore
    row, then redirects to the login page. ``save_session`` deletes the
    cookie on the response because the session is now empty.
    """
    session_id = getattr(session, 'sessionID', None)
    session.clear()
    session.modified = True
    if session_id:
        store = db.session.get(db.SessionStore, session_id)
        if store is not None:
            db.session.delete(store)
            db.session.commit()
    return redirect(url_for('admin.admin_login'))


@admin.route("/logged_in")
@verify_admin
def admin_logged_in():
    """Polled by template_admin.html every 5s to detect session expiry.
    """
    return "True"


@admin.route("/login", methods=['GET', 'POST'])
def admin_login():
    if session.get('loggedIn', False):
        # Already authenticated — mint the preview participant lazily so
        # that admins who use preview routes still have one cached on the
        # session, without creating a row for anonymous GETs.
        _ensure_preview_participant()
        return redirect(url_for("admin.route_progress"))

    if request.method == 'POST':
        from BOFS.services import brute_force
        ip = brute_force.get_client_ip()
        submitted = request.form.get('password', '')
        expected = current_app.config['ADMIN_PASSWORD']
        if not hmac.compare_digest(submitted, expected):
            brute_force.record_failure(ip)
            return render_template("login_admin.html", message="The password you entered is incorrect.")
        else:
            brute_force.record_success_admin(ip)
            # Rotate the session ID before flipping loggedIn so an attacker
            # who planted a known session cookie pre-auth can't ride the
            # post-auth session (classic session fixation).
            current_app.session_interface.regenerate(current_app, session)
            session['loggedIn'] = True
            session['adminIp'] = ip
            session.modified = True
            _ensure_preview_participant()

        redirect_to = url_for("admin.route_progress")

        r = request.args.get('r')
        if r and _REDIRECT_ENDPOINT_RE.match(r):
            try:
                redirect_to = url_for("admin." + r)
            except BuildError:
                # Unknown endpoint — fall back to the default landing page.
                pass

        return redirect(redirect_to)
    else:
        return render_template("login_admin.html")


def _ensure_preview_participant():
    """Create the admin's preview participant row if one isn't already on the
    session. Called only after authentication so anonymous probes can't mint
    participants — that would let an attacker skew condition counts without
    ever proving they hold the admin password."""
    if 'participantID' in session:
        return
    p = provide_consent(True)
    p.excludeFromCount = True
    db.session.commit()


@admin.route("/progress")
@verify_admin
def route_progress():
    pages, progress = AdminStatsService.fetch_progress()
    summary_groups, summary = AdminStatsService.fetch_progress_summary()
    end_reason_counts = AdminStatsService.fetch_end_reason_counts()

    return render_template("progress.html",
                           pages=pages, progress=progress,
                           show_source=_should_show_source(progress),
                           summary_groups=summary_groups, summary=summary,
                           end_reason_counts=end_reason_counts,
                           display_time=display_time)


@admin.route("/progress_ajax")
@verify_admin
def route_progress_ajax():
    pages, progress = AdminStatsService.fetch_progress()
    return render_template("progress_ajax.html", pages=pages, progress=progress,
                           show_source=_should_show_source(progress))


def _should_show_source(progress) -> bool:
    """Show the Source column only when participants differ on it.

    Hides the column when every row carries the same source value
    (including the all-NULL case for studies that don't use ?source=) so
    the table doesn't widen with a column that carries no information.
    """
    return len({r.Participant.source for r in progress}) > 1


@admin.route("/progress_summary_ajax")
@verify_admin
def route_progress_summary_ajax():
    summary_groups, summary = AdminStatsService.fetch_progress_summary()
    end_reason_counts = AdminStatsService.fetch_end_reason_counts()
    return render_template("progress_summary_ajax.html",
                           summary_groups=summary_groups, summary=summary,
                           end_reason_counts=end_reason_counts,
                           display_time=display_time)


@admin.route("/condition/<int:condition_num>/toggle", methods=['POST'])
@verify_admin
def route_toggle_condition(condition_num):
    conditions = current_app.config.get('CONDITIONS', [])
    idx = condition_num - 1
    if idx < 0 or idx >= len(conditions):
        return "Invalid condition", 400

    ParticipantService.toggle_condition_enabled(idx)

    summary_groups, summary = AdminStatsService.fetch_progress_summary()
    end_reason_counts = AdminStatsService.fetch_end_reason_counts()
    return render_template("progress_summary_ajax.html",
                           summary_groups=summary_groups, summary=summary,
                           end_reason_counts=end_reason_counts,
                           display_time=display_time)


def _question_text_lookup(questionnaire):
    """Build a {field_id: prompt_text} map from a questionnaire's JSON definition.
    Falls back to the field id if no readable prompt is available."""
    lookup = {}
    qjson = getattr(questionnaire, 'json_data', None) or {}

    def grab_text(defn):
        for key in ('q_text', 'text', 'prompt', 'label', 'title'):
            value = defn.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    for q in qjson.get('questions', []):
        # Single-field question
        if 'id' in q:
            lookup[q['id']] = grab_text(q) or q['id']

        # Group of sub-questions (e.g., radio grid)
        if isinstance(q.get('questions'), list):
            for sub in q['questions']:
                if isinstance(sub, dict) and 'id' in sub:
                    lookup[sub['id']] = grab_text(sub) or sub['id']

    return lookup


def _format_response_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value


def _resolve_view_for_path(url_path):
    """Match a PAGE_LIST path against the URL map and return the view
    function it routes to, or None if no rule matches. Used to find the
    handler that owns a custom page so we can read attributes the user
    stamped onto it (e.g. ``@page_tables``)."""
    try:
        adapter = current_app.url_map.bind('localhost')
        endpoint, _ = adapter.match('/' + url_path.lstrip('/'))
    except Exception:
        return None
    return current_app.view_functions.get(endpoint)


def _compute_export_section(participant, export_definition):
    """Run a single export definition for one participant and shape the result
    for template rendering. ``export_definition`` is a dict from
    ``JSONTable.create_exports_dict()`` — i.e. it already has the ``table``
    key annotated, plus ``fields`` and optionally ``filter`` / ``group_by`` /
    ``order_by`` / ``having``."""
    # Reuse Results.create_export_base_query — it doesn't touch instance state,
    # so skip __init__ to avoid running a full export against the whole DB.
    helper = Results.__new__(Results)
    try:
        levels, fields, base_query = helper.create_export_base_query(export_definition)
    except Exception as exc:
        return {
            'filter': export_definition.get('filter', ''),
            'group_by': export_definition.get('group_by', ''),
            'error': str(exc),
            'rows': [],
        }

    query = base_query.filter(db.literal_column('participantID') == participant.participantID)
    result_rows = query.all()
    if not result_rows:
        return None

    # ``levels`` and ``result_rows`` come from two independent SELECTs and
    # are not guaranteed to be in the same order. Index result_rows by
    # the group_by key tuple so each level pairs with its matching row
    # by value, not by position.
    group_by_def = export_definition.get('group_by', '')
    if isinstance(group_by_def, list):
        group_by_cols = list(group_by_def)
    elif isinstance(group_by_def, str) and group_by_def:
        group_by_cols = [group_by_def]
    else:
        group_by_cols = []

    def _key(obj):
        return tuple(getattr(obj, col, None) for col in group_by_cols)

    output_rows = []
    if levels:
        result_by_key = {_key(r): r for r in result_rows}
        for level in levels:
            row = result_by_key.get(_key(level))
            if row is None:
                # Participant has no data at this level — skip rather
                # than emit a placeholder.
                continue
            level_label = "_".join(str(x) for x in level)
            output_rows.append({
                'level': level_label,
                'fields': [
                    {'name': f, 'value': _format_response_value(getattr(row, f, None))}
                    for f in fields
                ],
            })
    else:
        row = result_rows[0]
        output_rows.append({
            'level': None,
            'fields': [
                {'name': f, 'value': _format_response_value(getattr(row, f, None))}
                for f in fields
            ],
        })

    return {
        'filter': export_definition.get('filter', ''),
        'group_by': export_definition.get('group_by', ''),
        'rows': output_rows,
    }


def _fetch_table_rows(participant, table_names):
    """Return a list of {name, sections} dicts — one per named JSONTable that
    has both an ``exports`` block and at least one matching row for this
    participant. Each section is the output of one export definition (a single
    ``fields`` row, or one row per ``group_by`` level)."""
    tables_data = []
    for name in table_names:
        table = current_app.tables.get(name)
        if table is None or table.db_class is None:
            continue
        exports = table.create_exports_dict()
        if not exports:
            continue
        sections = []
        for export in exports:
            section = _compute_export_section(participant, export)
            if section:
                sections.append(section)
        if not sections:
            continue
        tables_data.append({
            'name': name,
            'sections': sections,
        })
    return tables_data


def _fetch_page_data(participant, page):
    """Return a dict describing the data submitted for this page, or None.
    Handles questionnaire pages and any custom page whose view function is
    decorated with ``@page_tables(...)``."""
    path = page['path']
    if not path.startswith('questionnaire/'):
        view = _resolve_view_for_path(path)
        table_names = getattr(view, '_bofs_tables', None) if view else None
        if not table_names:
            return None
        tables_data = _fetch_table_rows(participant, table_names)
        if not tables_data:
            return None
        return {'kind': 'tables', 'tables': tables_data}

    name_and_tag = current_app.page_list.extract_questionnaire_from_path(path, include_tag=True)
    name, tag = questionnaire_name_and_tag(name_and_tag)

    questionnaire = current_app.questionnaires.get(name)
    if questionnaire is None or questionnaire.db_class is None:
        return None

    row = db.session.query(questionnaire.db_class).filter(
        questionnaire.db_class.participantID == participant.participantID,
        questionnaire.db_class.tag == tag,
    ).first()

    if row is None:
        return None

    prompts = _question_text_lookup(questionnaire)
    fields = []
    for column in questionnaire.fetch_fields():
        fields.append({
            'id': column.id,
            'prompt': prompts.get(column.id, column.id),
            'value': _format_response_value(getattr(row, column.id, None)),
        })

    calculated = []
    for calc_name in questionnaire.get_calculated_fields():
        try:
            value = getattr(row, calc_name)()
        except Exception as e:
            value = f"<calculation error: {e}>"
        calculated.append({'id': calc_name, 'value': _format_response_value(value)})

    return {
        'kind': 'questionnaire',
        'name': name,
        'tag': tag,
        'fields': fields,
        'calculated': calculated,
    }


@admin.route("/participant/<int:pid>")
@verify_admin
def route_participant_detail(pid):
    participant = db.session.get(db.Participant, pid)
    if participant is None:
        return render_template("error.html",
                               title="Participant not found",
                               heading="Participant not found",
                               message=f"No participant exists with ID {pid}."), 404

    # Pass 0 (not None) when the participant has no condition assigned —
    # passing None falls back to the admin's session condition, which is
    # wrong. participant_id=None disables show_if filtering so that pages
    # the participant actually visited still appear here even if their
    # current data would now route them to a different branch (e.g. they
    # went back and changed an earlier answer). Pages they never visited
    # show as not_reached via the Progress join below.
    pages = current_app.page_list.flat_page_list(
        condition=participant.condition or 0,
        participant_id=None,
    )
    progress_rows = db.session.query(db.Progress) \
        .filter(db.Progress.participantID == pid).all()
    progress_by_path = {row.path: row for row in progress_rows}

    timeline = []
    for idx, page in enumerate(pages, start=1):
        path = page['path']
        progress = progress_by_path.get(path)
        started_on = progress.startedOn if progress else None
        submitted_on = progress.submittedOn if progress else None

        # Special cases: consent-style entry pages and the end page never get
        # a normal Progress row that reflects the experiment's actual flow.
        # Entry pages run before the participant is recorded in the DB, so no
        # Progress row is created. The end page sets participant.timeEnded but
        # never POSTs, so submittedOn stays NULL.
        if path in ('consent', 'consent_nc', 'create_participant', 'create_participant_nc'):
            started_on = participant.timeStarted
            submitted_on = participant.timeStarted
            status = 'completed'
        elif path == 'end' and participant.finished:
            started_on = started_on or participant.timeEnded
            submitted_on = participant.timeEnded
            status = 'completed'
        elif progress is None:
            status = 'not_reached'
        elif submitted_on is None:
            status = 'in_progress'
        else:
            status = 'completed'

        if started_on and submitted_on and submitted_on > started_on:
            duration_display = display_time((submitted_on - started_on).total_seconds())
        else:
            duration_display = ""

        timeline.append({
            'index': idx,
            'name': page.get('name', path),
            'path': path,
            'started_on': started_on,
            'submitted_on': submitted_on,
            'duration_display': duration_display,
            'status': status,
            'data': _fetch_page_data(participant, page),
        })

    return render_template("participant_detail.html",
                           participant=participant,
                           timeline=timeline,
                           total_pages=len(pages),
                           display_time=display_time)

@admin.post("/update_exclude_from_count")
@verify_admin
def route_update_exclude_from_count():
    if 'participantID' not in request.form or 'excludeFromCount' not in request.form:
        return ""

    p = db.session.get(db.Participant, request.form['participantID'])
    if p is None:
        return Response(status=404)
    p.excludeFromCount = not (request.form['excludeFromCount'] == 'True')
    db.session.commit()

    return Response(status=200, headers={'HX-Trigger': 'excludeChanged'})

@admin.route("/export_item_timing")
@admin.route("/export_item_timing/download")
@verify_admin
def route_export_item_timing():
    # The CSV header used to use "mTurkID" instead of "externalID".
    # This could potentially be a breaking change for researchers who had scripts looking for that CSV column by name.
    header = ["participantID", "externalID", "questionnaire", "tag",
              "questionID", "eventType", "timestamp", "value"]
    rows = [header]

    participants = db.session.query(db.Participant).filter(
        db.Participant.finished == True
    ).all()

    for p in participants:
        interactions = db.session.query(db.QuestionnaireInteraction).filter(
            db.QuestionnaireInteraction.participantID == p.participantID
        ).order_by(db.QuestionnaireInteraction.timestamp).all()

        mturk = p.externalID.strip() if p.externalID else ""
        for i in interactions:
            rows.append([
                p.participantID, mturk, i.questionnaire, i.tag,
                i.questionID, i.eventType, i.timestamp.isoformat(), i.value or ""
            ])

    data = csv_string(rows)

    if request.path.endswith("/download"):
        return Response(data, mimetype="text/csv", headers={
            "Content-disposition":
                f"attachment; filename=interaction_timing_{utcnow_naive().strftime('%Y-%m-%d')}.csv"
        })
    return render_template("export_csv.html", data=data)


def _used_binds_for_export(results):
    """Return the sorted list of non-default bind names that actually have
    data for the export — i.e. at least one column was registered for that
    bind by a loaded questionnaire or table. A configured-but-unreferenced
    bind has no columns (the unused-bind startup warning tells the operator
    about that case)."""
    return sorted({
        bk for bk in results.column_list_by_bind
        if bk is not None and results.column_list_by_bind.get(bk)
    })


def _df_with_formula_safe_strings(df):
    """Copy *df* with string-typed cells prefixed against CSV formula
    injection. Pandas' to_csv handles RFC 4180 quoting; the formula sigils
    (=+-@\\t) are a spreadsheet-app concern to_csv doesn't know about.
    """
    safe = df.copy()
    for col in safe.select_dtypes(include='object').columns:
        safe[col] = safe[col].map(
            lambda v: formula_safe(v) if isinstance(v, str) else v
        )
    return safe


@admin.route("/export")
@admin.route("/export/download", endpoint="route_export_download")
@verify_admin
def route_export():
    """Export preview for the default-bind data, or — when ``?bind=NAME``
    is supplied — a preview restricted to that bind. The download URL on
    the page targets the same bind so the preview and the CSV stay in
    sync.

    When no binds are configured (today's common case), the preview and
    the download both look exactly like they did before per-bind support
    landed. When binds *are* configured, the default-bind download
    excludes any PII / archive columns — those live behind their own
    ``/admin/export/download/<bind>`` endpoints.
    """
    unfinished_count = db.session.query(db.Participant). \
        filter(db.Participant.finished == False).count()  # For display only
    excluded_count = db.session.query(db.Participant). \
        filter(db.Participant.excludeFromCount == True).count()  # For display only

    results = Results(Results.build_filter_from_args(request.args))
    used_binds = _used_binds_for_export(results)
    has_binds = bool(used_binds)

    bind_arg = request.args.get("bind")
    # ``bind`` query arg picks which bind's data to preview. None / empty
    # / unrecognised means the default bind. Passing an unknown bind isn't
    # an error — the user might have removed it after opening the page —
    # we just fall back to default rather than 404ing the preview UI.
    selected_bind = bind_arg if bind_arg in used_binds else None

    if request.base_url.endswith("/download"):
        if has_binds:
            # Privacy default once binds exist: even the default-bind
            # download endpoint must not leak PII columns.
            df = results.build_data_frame_for_bind(None)
        else:
            df = results.build_data_frame()
        df_safe = _df_with_formula_safe_strings(df)
        return Response(
            df_safe.to_csv(na_rep="", index=False),
            mimetype="text/csv",
            headers={
                "Content-disposition": "attachment; filename=%s.csv" %
                                       ("export_" + utcnow_naive().strftime("%Y-%m-%d_%H-%M"))
            },
        )

    # Preview
    if has_binds:
        df = results.build_data_frame_for_bind(selected_bind)
    else:
        df = results.build_data_frame()

    if selected_bind is None:
        download_url = url_for("admin.route_export_download")
        bind_label = "Main Database"
    else:
        download_url = url_for("admin.route_export_download_bind", bind=selected_bind)
        bind_label = selected_bind

    return render_template(
        "export.html",
        data_table=df.to_html(index=False, classes="table table-striped border", justify="left", na_rep=""),
        rowCount=len(df),
        unfinishedCount=unfinished_count,
        excludedCount=excluded_count,
        has_binds=has_binds,
        used_binds=used_binds,
        selected_bind=selected_bind,
        bind_label=bind_label,
        download_url=download_url,
    )


@admin.route("/export/download/<bind>", endpoint="route_export_download_bind")
@verify_admin
def route_export_download_bind(bind):
    """Download a CSV containing only the columns owned by *bind*.

    Joinable on ``participantID`` to the default-bind CSV at
    ``/admin/export/download``. Returns 404 if the bind isn't configured.
    """
    configured = current_app.config.get("SQLALCHEMY_BINDS", {}) or {}
    if bind not in configured:
        from flask import abort
        abort(404)

    results = Results(Results.build_filter_from_args(request.args))
    df = results.build_data_frame_for_bind(bind)
    df_safe = _df_with_formula_safe_strings(df)
    return Response(
        df_safe.to_csv(na_rep="", index=False),
        mimetype="text/csv",
        headers={
            "Content-disposition": (
                f"attachment; filename=export_{bind}_"
                f"{utcnow_naive().strftime('%Y-%m-%d_%H-%M')}.csv"
            )
        },
    )


@admin.route("/results")
@verify_admin
def route_results():
    cache_path = os.path.join(current_app.root_path, 'cached_results.json')
    results, df, summary_stats = Results.calculate_results(cache_path)

    return render_template("results.html", summary_stats=summary_stats)


@admin.route("/results_boxplot/<path:field_name>")
@verify_admin
def route_results_boxplot(field_name: str):
    cache_path = os.path.join(current_app.root_path, 'cached_results.json')
    results, df, summary_stats = Results.calculate_results(cache_path)

    unique_conditions = df['condition'].unique().tolist()
    unique_conditions.sort()
    plot_data = []

    for condition in unique_conditions:
        df_part = df.loc[df.condition == condition]
        #count = df_part.count()

        data = {
            "y": df_part[field_name].to_list(),
            #"x": [condition] * count,
            "name": str(condition),
            "type": "box",
            "boxpoints": "Outliers"
        }
        plot_data.append(data)

    return render_template("results_boxplot.html", field_name=field_name, plot_data=plot_data)


@admin.route("/preview_procedure", methods=["GET", "POST"])
@verify_admin
def route_preview_procedure():
    #questionnaires = current_app.page_list.parse_list_into_procedure()
    mermaid_string = current_app.page_list.to_mermaid()

    #try:
    #    f = open(current_app.get_questionnaire_path(questionnaireName), 'r')
    #    json_data = f.read()
    #    json_data = json.loads(json_data)
    #    f.close()
    #
    #except Exception as e:
    #    errors = list(e.args)
    #
    #return JSONQuestionnaire.render_unloaded_questionnaire(json_data, "preview_questionnaire.html", errors=errors)

    return render_template("procedure.html", mermaid_string=mermaid_string)

@admin.route("/preview_questionnaire/<questionnaireName>", methods=["GET", "POST"])
@verify_admin
def route_preview_questionnaire(questionnaireName):
    if request.method == 'POST' and 'condition' in request.form:
        session['condition'] = int_or_0(request.form['condition'])

        p = db.session.get(db.Participant, session['participantID'])
        p.condition = session['condition']
        db.session.commit()

    errors = []
    json_data = None

    try:
        with open(current_app.get_questionnaire_path(questionnaireName), 'r') as f:
            json_data = json.loads(f.read())
    except Exception as e:
        errors = list(e.args)

    return ParticipantQuestionnaireService.render_unloaded_questionnaire(json_data, "preview_questionnaire.html", errors=errors)


@admin.route("/questionnaire_html/<questionnaireName>")
@verify_admin
def route_questionnaire_html(questionnaireName):
    errors = []
    json_data = None

    try:
        with open(current_app.get_questionnaire_path(questionnaireName), 'r') as f:
            json_data = json.loads(f.read())
    except Exception as e:
        errors = list(e.args)

    return ParticipantQuestionnaireService.render_unloaded_questionnaire(json_data, "preview_questionnaire_simple.html", errors=errors)


def _find_table(tableName):
    """Find a Table object across every bind's MetaData.

    Cross-bind tables don't live in ``db.metadata`` — Flask-SQLAlchemy 3.x
    keeps one MetaData per bind in ``db.metadatas``. Returns
    ``(table, bind_key)`` (with ``bind_key`` ``None`` for the default
    bind) or ``(None, None)`` if no bind has a table by that name.
    """
    for bk, md in db.metadatas.items():
        if tableName in md.tables:
            return md.tables[tableName], bk
    return None, None


def table_data(tableName):
    if tableName in _TABLE_VIEW_BLOCKED:
        abort(404)
    table, bind_key = _find_table(tableName)
    if table is None:
        abort(404)

    # ``db.session.query(table)`` against a bare Table object loses the
    # bind information (only models carry ``__bind_key__``), so the
    # session would default to the main engine and 'no such table' for
    # cross-bind tables. Execute against the engine that actually owns it.
    from sqlalchemy import select
    engine = db.engine if bind_key is None else db.engines[bind_key]
    with engine.connect() as conn:
        rows = list(conn.execute(select(table)))

    columns = []

    for c in table.columns:
        type = str(c.type)
        if type.startswith("VARCHAR") or type.startswith("TEXT"):
            type = u"string"

        column = {'name': c.description, 'type': type.lower()}

        columns.append(column)

    return columns, rows


@admin.route("/table_view/<tableName>")
@verify_admin
def route_table_view(tableName):
    columns, rows = table_data(tableName)
    return render_template("table_view.html", tableName=tableName, rows=rows, columns=columns)


@admin.route("/table_ajax/<tableName>")
@verify_admin
def route_table_ajax(tableName):
    columns, rows = table_data(tableName)
    return render_template("table_ajax.html", rows=rows, columns=columns)


@admin.route("/table_csv/<tableName>")
@verify_admin
def route_table_csv(tableName):
    columns, rows = table_data(tableName)

    headers = [c['name'] for c in columns]
    body_rows = [[row[i] for i in range(len(columns))] for row in rows]

    return Response(csv_string([headers] + body_rows),
                    mimetype="text/csv",
                    headers={
                        "Content-disposition": "attachment; filename=%s.csv" % (
                                    tableName + "_" + utcnow_naive().strftime("%Y-%m-%d"))
                    })


def _resolve_sqlite_uri(uri):
    """Return the absolute SQLite DB path for *uri* if it resolves under
    the project root, otherwise ``None``. The project-root containment
    check guards against hostile or mistakenly-configured URIs like
    ``sqlite:///../../etc/passwd`` reaching backup/delete operations.
    """
    if not isinstance(uri, str) or not uri.startswith('sqlite:///'):
        return None
    rel = uri.replace('sqlite:///', '')
    project_root = os.path.abspath(current_app.root_path)
    resolved = os.path.abspath(os.path.join(project_root, rel))
    if os.path.commonpath([resolved, project_root]) != project_root:
        return None
    return resolved


def _sqlite_db_paths():
    """Yield ``(bind_key, absolute_path)`` for every SQLite-backed bind
    whose file exists on disk and resolves under the project root.

    ``bind_key`` is ``None`` for the default database. Non-SQLite binds
    (Postgres, MySQL) are skipped — they have no file to back up or
    delete through this UI; an operator with those binds has to wipe
    them through their respective DB tools.
    """
    seen = set()
    entries = [(None, current_app.config.get('SQLALCHEMY_DATABASE_URI'))]
    for bk, uri in (current_app.config.get('SQLALCHEMY_BINDS') or {}).items():
        entries.append((bk, uri))
    for bk, uri in entries:
        resolved = _resolve_sqlite_uri(uri)
        if resolved is None or not os.path.exists(resolved):
            continue
        if resolved in seen:
            # Defensive: two binds pointing at the same file would
            # otherwise produce duplicate zip entries.
            continue
        seen.add(resolved)
        yield bk, resolved


def _backup_basename(prefix):
    """``<prefix>_YYYYmmdd_HHMMSS.zip`` — matches the timestamp format used
    elsewhere in the admin for download filenames so a researcher can sort
    their downloads by name."""
    return f"{prefix}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.zip"


def _build_databases_zip():
    """Return ``(bytes, paths)`` where *bytes* is a zip of every SQLite
    bind file and *paths* is the list of paths included. Empty *paths*
    means nothing was zippable (no SQLite binds or no files on disk yet).
    """
    import io
    import zipfile
    buf = io.BytesIO()
    paths = []
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for _bk, resolved in _sqlite_db_paths():
            zf.write(resolved, arcname=os.path.basename(resolved))
            paths.append(resolved)
    return buf.getvalue(), paths


@admin.route("/database_download")
@verify_admin
def route_database_download():
    """Download every SQLite-backed database as a single ZIP.

    Researchers with multiple binds (e.g. a PII bind) get all files in
    one shot — backing up via this endpoint can't silently miss the
    second file the way a single-file download would.
    """
    if not current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'):
        return "Not using a SQLite database."

    zip_bytes, paths = _build_databases_zip()
    if not paths:
        return Response("No SQLite database files were found.", status=404)

    return Response(
        zip_bytes,
        mimetype="application/zip",
        headers={
            "Content-disposition":
                f"attachment; filename={_backup_basename('databases')}"
        },
    )


@admin.route("/database_delete", methods=['GET', 'POST'])
@verify_admin
def route_database_delete():
    """Clear rows from every configured bind.

    Before clearing, a timestamped ZIP backup of every SQLite-backed
    bind is written to the project root. The backup is automatic — a
    researcher who clicks Delete and immediately regrets it can recover
    by unzipping that file back over the live DBs.

    Like the pre-bind version, this clears *rows* from every table; the
    schemas stay in place so ``db.create_all()`` on the next startup
    doesn't have to re-create anything.
    """
    if not current_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'):
        return "Not using a SQLite database."

    if request.method == 'POST':
        from BOFS.services import brute_force
        ip = brute_force.get_client_ip()
        submitted = request.form.get('password', '')
        expected = current_app.config['ADMIN_PASSWORD']
        if not hmac.compare_digest(submitted, expected):
            # Rate-limit the secondary password challenge so a stolen admin
            # session can't grind it offline-style.
            brute_force.record_failure(ip)
            return render_template("database_delete.html", message="The password you entered is incorrect.")

        # Write the backup before touching anything. If the zip can't be
        # written (disk full, permission denied), abort the delete — a
        # silent half-deletion with no recovery file is exactly what the
        # backup is meant to prevent.
        zip_bytes, paths = _build_databases_zip()
        if not paths:
            return Response(
                "No SQLite database files were found to back up.",
                status=500,
            )
        project_root = os.path.abspath(current_app.root_path)
        backup_path = os.path.join(project_root, _backup_basename('backup'))
        try:
            with open(backup_path, 'wb') as f:
                f.write(zip_bytes)
        except OSError as e:
            current_app.logger.exception(
                "database_delete: backup write failed (%s); aborting delete.", e,
            )
            return Response(
                f"Backup could not be written ({e}); delete aborted.",
                status=500,
            )

        # Clear rows from every bind. ``db.session.query(tbl).delete()``
        # against a bare Table loses bind information; route the delete
        # through the engine that owns each MetaData.
        for bk, md in db.metadatas.items():
            engine = db.engine if bk is None else db.engines[bk]
            with engine.begin() as conn:
                for tbl in reversed(md.sorted_tables):
                    conn.execute(tbl.delete())
        db.session.commit()

        current_app.logger.info(
            "database_delete: cleared rows from %d bind(s); backup at %s",
            len(list(db.metadatas)), backup_path,
        )
        return redirect(url_for("admin.route_progress"))

    return render_template("database_delete.html")


