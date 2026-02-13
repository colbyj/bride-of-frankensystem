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
def invalid_questionnaires():
    """Sample invalid questionnaire JSON data for validation testing."""
    return {
        "missing_questions_key": {
            "title": "Bad Questionnaire",
            "instructions": "This has no questions key",
        },
        "invalid_question_type": {
            "questions": [{"questiontype": "magical_widget", "id": "test"}]
        },
        "duplicate_ids": {
            "questions": [
                {"questiontype": "field", "id": "duplicate"},
                {"questiontype": "field", "id": "duplicate"},
            ]
        },
        "unsafe_field_id": {
            "questions": [
                {"questiontype": "field", "id": "123invalid"},
                {"questiontype": "field", "id": "has-dash"},
                {"questiontype": "field", "id": "has space"},
            ]
        },
        "reserved_column": {
            "questions": [{"questiontype": "field", "id": "participantID"}]
        },
        "broken_calculation": {
            "questions": [{"questiontype": "slider", "id": "q1"}],
            "participant_calculations": {"total": "q1 + nonexistent_field"},
        },
    }


# ===========================================================================
# Tier 2 helper — write a questionnaire JSON to the app's questionnaires dir
# ===========================================================================

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
