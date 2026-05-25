import json
import os

import pytest
import toml


# ===========================================================================
# Tier 2 fixtures — minimal BOFS app with in-memory SQLite
# ===========================================================================

@pytest.fixture
def bofs_app(tmp_path):
    """
    Create a minimal BOFS Flask app backed by in-memory SQLite.

    Yields the app with an active application context pushed.
    Restores the original working directory on teardown.
    """
    # Write a minimal config.toml
    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    # Create required directories
    (tmp_path / "questionnaires").mkdir()

    # Write a minimal consent.html (required by BOFSFlask URL rule)
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    # Save and restore the working directory (create_app does os.chdir)
    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=True)

    ctx = app.app_context()
    ctx.push()
    app.db.create_all()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)



@pytest.fixture
def bofs_app_with_binds(tmp_path):
    """
    BOFS app with a non-default SQLALCHEMY_BINDS entry ("pii") backed by a
    separate in-memory SQLite engine. Use for per-bind tests.

    Both engines are :memory:, so each test starts with empty databases.
    """
    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_BINDS": {
            "pii": "sqlite:///:memory:",
        },
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    (tmp_path / "questionnaires").mkdir()
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=True)

    ctx = app.app_context()
    ctx.push()
    app.db.create_all()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


# ===========================================================================
# Tier 2 helper — write a questionnaire JSON to the app's questionnaires dir
# ===========================================================================

def write_table_file(app, name, data):
    """
    Write a table JSON into the app's tables/ directory
    and load it into the app. Returns the JSONTable instance.
    """
    tables_dir = os.path.join(app.root_path, "tables")
    os.makedirs(tables_dir, exist_ok=True)
    filepath = os.path.join(tables_dir, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    from BOFS.JSONTable import JSONTable
    t = JSONTable(tables_dir, name)
    t.create_db_class()

    if not hasattr(app.db, t.db_class.__name__):
        setattr(app.db, t.db_class.__name__, t.db_class)
    app.tables[name] = t
    app.db.create_all()
    return t


def write_questionnaire_file(app, name, data):
    """
    Write a questionnaire JSON into the app's questionnaires/ directory
    and load it into the app. Returns the JSONQuestionnaire instance.
    """
    q_dir = os.path.join(app.root_path, "questionnaires")
    filepath = os.path.join(q_dir, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    from BOFS.JSONQuestionnaire import JSONQuestionnaire
    q = JSONQuestionnaire(q_dir, name, is_in_db=True)
    q.create_db_class()

    # Register the model on the db so SQLAlchemy knows about it
    setattr(app.db, "Questionnaire" + q.db_class.__name__, q.db_class)
    app.questionnaires[name] = q
    app.db.create_all()

    return q


# ===========================================================================
# Tier 1 fixtures — pure data, no Flask context
# ===========================================================================

@pytest.fixture
def simple_page_list_data():
    """A basic linear page list with no conditional routing."""
    return [
        {'name': 'Consent', 'path': 'consent'},
        {'name': 'Survey', 'path': 'questionnaire/example'},
        {'name': 'Survey', 'path': 'questionnaire/example_grid'},
        {'name': 'End', 'path': 'end'},
    ]


@pytest.fixture
def conditional_page_list_data():
    """A page list with conditional routing for 2 conditions."""
    return [
        {'name': 'Consent', 'path': 'consent'},
        {'name': 'Pre Survey', 'path': 'questionnaire/pre/before'},
        {'conditional_routing': [
            {
                'condition': 1,
                'page_list': [
                    {'name': 'Control Task', 'path': 'questionnaire/control_q'},
                    {'name': 'Control Follow-up', 'path': 'questionnaire/control_followup'},
                ]
            },
            {
                'condition': 2,
                'page_list': [
                    {'name': 'Treatment Task', 'path': 'questionnaire/treatment_q'},
                ]
            },
        ]},
        {'name': 'Post Survey', 'path': 'questionnaire/post'},
        {'name': 'End', 'path': 'end'},
    ]


@pytest.fixture
def sample_questionnaire_json():
    """A questionnaire JSON structure covering multiple question types."""
    return {
        "title": "Test Questionnaire",
        "instructions": "Please answer each question.",
        "code": "",
        "questions": [
            {
                "questiontype": "textview",
                "title": "Info",
                "text": "This is informational text."
            },
            {
                "questiontype": "radiogrid",
                "instructions": "Rate each item.",
                "id": "grid_1",
                "labels": ["Disagree", "", "Neutral", "", "Agree"],
                "q_text": [
                    {"id": "g1_q1", "text": "Item one"},
                    {"id": "g1_q2", "text": "Item two"},
                ]
            },
            {
                "questiontype": "radiolist",
                "instructions": "Choose one.",
                "id": "radio_1",
                "labels": ["Yes", "No"]
            },
            {
                "questiontype": "slider",
                "instructions": "Slide to rate.",
                "id": "slider_1",
                "left": "Low",
                "right": "High"
            },
            {
                "questiontype": "checklist",
                "instructions": "Check all that apply.",
                "id": "check_1",
                "questions": [
                    {"id": "cl_1", "text": "Option A"},
                    {"id": "cl_2", "text": "Option B"},
                ]
            },
            {
                "questiontype": "field",
                "instructions": "Enter text.",
                "id": "text_1"
            },
            {
                "questiontype": "num_field",
                "instructions": "Enter a number.",
                "id": "num_1"
            },
            {
                "questiontype": "drop_down",
                "instructions": "Select one.",
                "id": "dd_1",
                "items": ["apple", "banana"]
            },
            {
                "questiontype": "multi_field",
                "instructions": "Enter a lot of text.",
                "id": "multi_1"
            },
        ]
    }


@pytest.fixture
def sample_questionnaire_with_calculations():
    """A questionnaire JSON with participant_calculations."""
    return {
        "title": "Calculated Questionnaire",
        "instructions": "",
        "code": "",
        "questions": [
            {
                "questiontype": "radiogrid",
                "instructions": "Rate your agreement",
                "id": "grid_1",
                "labels": ["Strongly disagree", "", "Neutral", "", "Strongly agree"],
                "q_text": [
                    {"id": "q1", "text": "Statement one"},
                    {"id": "q2", "text": "Statement two"},
                    {"id": "q3", "text": "Statement three"},
                ]
            }
        ],
        "participant_calculations": {
            "QualityMean": "mean([q1, 6-q2, q3])",
            "QualitySum": "q1 + 6-q2 + q3"
        }
    }


# ===========================================================================
# Tier 3 questionnaire JSON data (written to disk before create_app)
# ===========================================================================

SURVEY_QUESTIONNAIRE_FULL = {
    "title": "Test Survey",
    "instructions": "Answer all questions.",
    "questions": [
        {"questiontype": "field", "instructions": "Enter name", "id": "name"},
        {
            "questiontype": "slider",
            "instructions": "Rate",
            "id": "rating",
            "left": "Low",
            "right": "High",
        },
        {"questiontype": "num_field", "instructions": "Enter age", "id": "age"},
        {
            "questiontype": "radiogrid",
            "id": "grid",
            "instructions": "Rate items",
            "labels": ["1", "2", "3", "4", "5"],
            "q_text": [
                {"id": "g1_q1", "text": "Item one"},
                {"id": "g1_q2", "text": "Item two"},
            ],
        },
    ],
    "participant_calculations": {
        "grid_total": "g1_q1 + g1_q2",
    },
}

SIMPLE_QUESTIONNAIRE_MINIMAL = {
    "title": "Simple",
    "instructions": "",
    "questions": [
        {"questiontype": "field", "id": "answer"},
    ],
}


# ===========================================================================
# Tier 3 fixtures — BOFS app with questionnaires for integration testing
# ===========================================================================

@pytest.fixture
def bofs_app_with_questionnaires(tmp_path):
    """
    Create a BOFS app with questionnaires in PAGE_LIST and conditions configured.
    Suitable for Tier 3 integration tests using test_client.

    PAGE_LIST: consent → questionnaire/survey → questionnaire/survey/before → end
    """
    # Write questionnaire files BEFORE create_app so they're auto-discovered
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "survey.json").write_text(
        json.dumps(SURVEY_QUESTIONNAIRE_FULL), encoding="utf-8"
    )

    # consent.html static file (served by BOFSFlask.route_consent)
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
        "GENERATE_COMPLETION_CODE": True,
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Survey", "path": "questionnaire/survey"},
            {"name": "Survey", "path": "questionnaire/survey/before"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


@pytest.fixture
def bofs_app_for_export_with_binds(tmp_path):
    """BOFS app with two questionnaires: one on the default bind, one on a
    ``pii`` bind. PAGE_LIST includes both so ``page_list.get_questionnaire_list``
    yields them and the export pipeline picks them up.
    """
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "experiment.json").write_text(json.dumps({
        "title": "Experiment",
        "questions": [{"questiontype": "field", "id": "score"}],
    }), encoding="utf-8")
    (q_dir / "contact.json").write_text(json.dumps({
        "title": "Contact",
        "database": "pii",
        "questions": [{"questiontype": "field", "id": "email"}],
    }), encoding="utf-8")

    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_BINDS": {"pii": "sqlite:///:memory:"},
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": True,
        "BRUTE_FORCE_PROTECTION": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Experiment", "path": "questionnaire/experiment"},
            {"name": "Contact", "path": "questionnaire/contact"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


@pytest.fixture
def bofs_app_with_file_binds(tmp_path):
    """BOFS app with file-backed SQLite for the default *and* PII binds.

    Required for tests that exercise ``/admin/database_download`` and
    ``/admin/database_delete`` — those routes resolve real on-disk files
    via ``_resolve_sqlite_uri`` and skip ``:memory:`` URIs (which don't
    correspond to a file). Tests that don't care about on-disk artefacts
    should stay on ``bofs_app_for_export_with_binds`` (in-memory).
    """
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "experiment.json").write_text(json.dumps({
        "title": "Experiment",
        "questions": [{"questiontype": "field", "id": "score"}],
    }), encoding="utf-8")
    (q_dir / "contact.json").write_text(json.dumps({
        "title": "Contact",
        "database": "pii",
        "questions": [{"questiontype": "field", "id": "email"}],
    }), encoding="utf-8")
    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///main.db",
        "SQLALCHEMY_BINDS": {"pii": "sqlite:///pii.db"},
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": True,
        "BRUTE_FORCE_PROTECTION": False,
        # /admin/database_delete is a POST through the admin CSRF gate.
        # Disable here so tests can exercise the route without manually
        # threading a token through every request.
        "WTF_CSRF_ENABLED": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Experiment", "path": "questionnaire/experiment"},
            {"name": "Contact", "path": "questionnaire/contact"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


@pytest.fixture
def bofs_app_for_export_no_binds(tmp_path):
    """Backward-compat fixture: same questionnaires as bofs_app_for_export_with_binds
    but no SQLALCHEMY_BINDS and no ``database`` field on either questionnaire.
    Used to assert the single-CSV export path is byte-identical to before.
    """
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "experiment.json").write_text(json.dumps({
        "title": "Experiment",
        "questions": [{"questiontype": "field", "id": "score"}],
    }), encoding="utf-8")
    (q_dir / "contact.json").write_text(json.dumps({
        "title": "Contact",
        "questions": [{"questiontype": "field", "id": "email"}],
    }), encoding="utf-8")

    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": True,
        "BRUTE_FORCE_PROTECTION": False,
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"name": "Experiment", "path": "questionnaire/experiment"},
            {"name": "Contact", "path": "questionnaire/contact"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


@pytest.fixture
def bofs_app_with_conditions(tmp_path):
    """
    Create a BOFS app with conditional routing in PAGE_LIST.

    PAGE_LIST: consent → [cond 1: control | cond 2: treatment] → post → end
    """
    q_dir = tmp_path / "questionnaires"
    q_dir.mkdir()
    (q_dir / "control.json").write_text(
        json.dumps(SIMPLE_QUESTIONNAIRE_MINIMAL), encoding="utf-8"
    )
    (q_dir / "treatment.json").write_text(
        json.dumps(SIMPLE_QUESTIONNAIRE_MINIMAL), encoding="utf-8"
    )
    (q_dir / "post.json").write_text(
        json.dumps(SIMPLE_QUESTIONNAIRE_MINIMAL), encoding="utf-8"
    )

    (tmp_path / "consent.html").write_text("<p>Consent</p>", encoding="utf-8")

    config_data = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "TITLE": "Test Experiment",
        "ADMIN_PASSWORD": "test",
        "USE_ADMIN": False,
        "BRUTE_FORCE_PROTECTION": False,
        "CONDITIONS": [
            {"label": "Control", "enabled": True},
            {"label": "Treatment", "enabled": True},
        ],
        "PAGE_LIST": [
            {"name": "Consent", "path": "consent"},
            {"conditional_routing": [
                {
                    "condition": 1,
                    "page_list": [
                        {"name": "Control", "path": "questionnaire/control"},
                    ],
                },
                {
                    "condition": 2,
                    "page_list": [
                        {"name": "Treatment", "path": "questionnaire/treatment"},
                    ],
                },
            ]},
            {"name": "Post", "path": "questionnaire/post"},
            {"name": "End", "path": "end"},
        ],
    }
    config_path = tmp_path / "config.toml"
    config_path.write_text(toml.dumps(config_data), encoding="utf-8")

    original_cwd = os.getcwd()

    from BOFS.create_app import create_app
    app = create_app(str(tmp_path), str(config_path), debug=False)

    ctx = app.app_context()
    ctx.push()

    yield app

    app.db.drop_all()
    ctx.pop()
    os.chdir(original_cwd)


# ===========================================================================
# Tier 3 helpers — HTTP request helpers for integration tests
# ===========================================================================

def create_participant_via_consent(client, app, assign_condition=True):
    """
    POST to /consent (or /consent_nc), following redirects to advance navigation.
    Returns the participantID of the newly created participant.
    """
    path = "/consent" if assign_condition else "/consent_nc"
    client.post(path, follow_redirects=True)

    participant = app.db.session.query(app.db.Participant).order_by(
        app.db.Participant.participantID.desc()
    ).first()
    return participant.participantID


def submit_questionnaire_data(client, name, tag=None, data_dict=None,
                              follow_redirects=True):
    """
    POST form data to a questionnaire route.  Merges required hidden fields
    (timeStarted, questionnaireInteractions) with the provided *data_dict*.
    """
    if tag:
        url = f"/questionnaire/{name}/{tag}"
    else:
        url = f"/questionnaire/{name}"

    form_data = {
        "timeStarted": "2024-01-01 12:00:00",
        "questionnaireInteractions": "",
    }
    if data_dict:
        form_data.update(data_dict)

    return client.post(url, data=form_data, follow_redirects=follow_redirects)
