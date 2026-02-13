import pytest


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
