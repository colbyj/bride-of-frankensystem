"""
BOFS Init Wizard - Interactive project scaffolding for BOFS experiments.

This module provides an interactive CLI wizard for creating new BOFS projects
with customizable features. The feature system is designed for easy extension.
"""

import html
import os
import secrets
import shutil
from pathlib import Path
from typing import Optional

import questionary


# Feature definitions - easily extended by adding entries
FEATURES = {
    "external_id": {
        "label": "External ID page (MTurk/Prolific)",
        "description": "Collect participant IDs from recruitment platforms",
        "default": False,
        "config_lines": [
            "",
            "# External ID Settings",
            'EXTERNAL_ID_LABEL = "Participant ID"',
            'EXTERNAL_ID_PROMPT = "Please enter your participant ID from the recruitment platform."',
        ],
        "page_entry": {"name": "External ID", "path": "external_id"},
        "page_position": 1,  # After consent (index 0)
    },
    "instructions_page": {
        "label": "Instructions page",
        "description": "Static instruction page with automatic continue button",
        "default": False,
        "files": {
            "templates/instructions/welcome.html": '''<h1>Welcome</h1>

<p>Thank you for participating in this study.</p>

<p>On the following pages, you will be asked to complete a survey.
Please read each question carefully and answer honestly.</p>

<p>Click "Continue" below when you are ready to begin.</p>
''',
        },
        "page_entry": {"name": "Instructions", "path": "instructions/welcome"},
        "page_position": 2,  # After consent and external_id (if present)
    },
    "simple_page": {
        "label": "Simple custom page",
        "description": "Custom HTML page with manual navigation control",
        "default": False,
        "files": {
            "templates/simple/task.html": '''<h1>Task</h1>

<p>This is a simple custom page. You control the navigation.</p>

<p>Use this for tasks, interactive content, or any page where you need
full control over when participants can proceed.</p>

<!-- Navigation: link to advance to next page -->
<p><a href="/redirect_next_page" class="btn btn-primary">Continue</a></p>
''',
        },
        "page_entry": {"name": "Task", "path": "simple/task"},
        "page_position": 3,  # After instructions (if present)
    },
    "conditions": {
        "label": "Multiple conditions",
        "description": "Randomize participants into experimental groups",
        "default": False,
        "config_lines": [
            "",
            "# Conditions - participants will be randomly assigned",
            "CONDITIONS = [",
            "    {label='Control', enabled=true},",
            "    {label='Treatment', enabled=true}",
            "]",
        ],
        "files": {
            "questionnaires/survey_treatment.json": '''{
    "title": "Treatment Survey",
    "instructions": "Please answer the following questions about your experience with the treatment.",
    "questions": [
        {
            "questiontype": "radiogrid",
            "instructions": "Rate your agreement with the following statements.",
            "id": "treatment_agreement",
            "labels": [
                "Strongly disagree",
                "Disagree",
                "Neutral",
                "Agree",
                "Strongly agree"
            ],
            "q_text": [
                {
                    "id": "item1",
                    "text": "The treatment was effective"
                },
                {
                    "id": "item2",
                    "text": "I would recommend the treatment"
                },
                {
                    "id": "item3",
                    "text": "The treatment met my expectations"
                }
            ]
        }
    ]
}
''',
        },
    },
    "pre_post": {
        "label": "Pre/post questionnaires",
        "description": "Show the same questionnaire before and after (with tags)",
        "default": False,
        # This feature modifies the page list in build_page_list()
    },
    "custom_blueprint": {
        "label": "Custom blueprint (Python routes)",
        "description": "Create a starter Python file for custom routes",
        "default": False,
        "files": {
            "custom_routes/__init__.py": '''# This file makes custom_routes a Python package.
# BOFS auto-discovers blueprints from subdirectories.
''',
            "custom_routes/views.py": '''"""
Custom routes for your BOFS experiment.

This blueprint is auto-discovered by BOFS. Add your custom routes here.
The blueprint variable name must match the folder name (custom_routes).
"""

from flask import Blueprint, render_template


custom_routes = Blueprint(
    'custom_routes',
    __name__,
    template_folder='templates',
    url_prefix='/custom'
)


@custom_routes.route('/example')
def example():
    """Example custom route."""
    return render_template('custom_example.html')
''',
            "custom_routes/templates/custom_example.html": '''{% extends "template.html" %}

{% block content %}
<h1>Custom Page Example</h1>
<p>This is an example custom page. Edit custom_routes/templates/custom_example.html to customize.</p>
<p><a href="{{ url_for('default.route_redirect_next_page') }}">Continue</a></p>
{% endblock %}
''',
        },
        "page_entry": {"name": "Custom Page", "path": "custom/example"},
        "page_position": -2,  # Before the last item (End)
    },
    "example_questionnaires": {
        "label": "Example questionnaires",
        "description": "Include demo questionnaires showing different question types",
        "default": True,
        "files": {
            "questionnaires/demographics.json": '''{
    "title": "Demographics",
    "instructions": "Please answer the following questions about yourself.",
    "questions": [
        {
            "questiontype": "num_field",
            "instructions": "What is your age?",
            "id": "age",
            "min": 18,
            "max": 120
        },
        {
            "questiontype": "radiolist",
            "instructions": "What is your gender?",
            "id": "gender",
            "labels": [
                "Male",
                "Female",
                "Non-binary",
                "Prefer not to say"
            ]
        },
        {
            "questiontype": "drop_down",
            "instructions": "What is the highest level of education you have completed?",
            "id": "education",
            "items": [
                "Less than high school",
                "High school diploma or equivalent",
                "Some college",
                "Bachelor's degree",
                "Master's degree",
                "Doctoral degree",
                "Professional degree"
            ]
        }
    ]
}
''',
            "questionnaires/feedback.json": '''{
    "title": "Feedback",
    "instructions": "Please provide your feedback on this study.",
    "questions": [
        {
            "questiontype": "radiogrid",
            "instructions": "Rate your experience",
            "id": "experience",
            "labels": [
                "Strongly disagree",
                "",
                "Neutral",
                "",
                "Strongly agree"
            ],
            "q_text": [
                {
                    "id": "clear_instructions",
                    "text": "The instructions were clear"
                },
                {
                    "id": "appropriate_length",
                    "text": "The study was an appropriate length"
                },
                {
                    "id": "interesting",
                    "text": "The study was interesting"
                }
            ]
        },
        {
            "questiontype": "multi_field",
            "instructions": "Do you have any additional comments or feedback?",
            "id": "comments",
            "height": "100",
            "required": false
        }
    ]
}
''',
        },
    },
    "example_tables": {
        "label": "Example JSON tables",
        "description": "Include example JSONTable definitions for structured data",
        "default": False,
        "files": {
            "tables/responses.json": '''{
    "columns": {
        "trial_number": {
            "type": "integer",
            "default": 0
        },
        "stimulus": {
            "type": "string"
        },
        "response": {
            "type": "string"
        },
        "reaction_time": {
            "type": "float"
        },
        "correct": {
            "type": "boolean"
        }
    }
}
''',
        },
    },
}


def escape_toml_string(s: str) -> str:
    """Escape a string for use in single-quoted TOML values."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def validate_project_name(name: str) -> bool | str:
    """Validate project name. Returns True if valid, error message if not."""
    if not name:
        return "Name cannot be empty"
    if not name.replace("_", "").replace("-", "").isalnum():
        return "Name can only contain letters, numbers, underscores, and hyphens"
    if name[0].isdigit():
        return "Name cannot start with a number"
    if name.startswith("-") or name.startswith("_"):
        return "Name cannot start with a hyphen or underscore"
    # Windows reserved names
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                'LPT1', 'LPT2', 'LPT3', 'LPT4'}
    if name.upper() in reserved:
        return f"'{name}' is a reserved name on Windows"
    return True


def generate_secret_key() -> str:
    """Generate a secure random secret key."""
    return secrets.token_hex(32)


def build_page_list(selected_features: list[str], use_pre_post: bool) -> str:
    """Build the PAGE_LIST configuration based on selected features."""
    use_conditions = "conditions" in selected_features

    # Start with base pages
    pages = [
        {"name": "Consent", "path": "consent"},
    ]

    # Insert feature pages at their specified positions
    feature_pages = []
    for feature_key in selected_features:
        feature = FEATURES.get(feature_key, {})
        if "page_entry" in feature:
            feature_pages.append((feature.get("page_position", -1), feature["page_entry"]))

    # Sort by position (positive positions first, then negative)
    feature_pages.sort(key=lambda x: (x[0] < 0, x[0]))

    # Sort positive positions in descending order so earlier inserts don't shift later positions
    positive_pages = [(pos, page) for pos, page in feature_pages if pos >= 0]
    positive_pages.sort(key=lambda x: x[0], reverse=True)
    for pos, page in positive_pages:
        pages.insert(pos, page)

    # Add questionnaire pages (or conditional routing if conditions selected)
    if use_conditions:
        # Add conditional routing block - different questionnaires per condition
        if use_pre_post:
            pages.append({
                "conditional_routing": [
                    {"condition": 1, "page_list": [
                        {"name": "Survey (Before)", "path": "questionnaire/survey/before"},
                        {"name": "Survey (After)", "path": "questionnaire/survey/after"},
                    ]},
                    {"condition": 2, "page_list": [
                        {"name": "Survey (Before)", "path": "questionnaire/survey_treatment/before"},
                        {"name": "Survey (After)", "path": "questionnaire/survey_treatment/after"},
                    ]},
                ]
            })
        else:
            pages.append({
                "conditional_routing": [
                    {"condition": 1, "page_list": [
                        {"name": "Survey", "path": "questionnaire/survey"},
                    ]},
                    {"condition": 2, "page_list": [
                        {"name": "Survey", "path": "questionnaire/survey_treatment"},
                    ]},
                ]
            })
    elif use_pre_post:
        pages.append({"name": "Survey (Before)", "path": "questionnaire/survey/before"})
        pages.append({"name": "Survey (After)", "path": "questionnaire/survey/after"})
    else:
        pages.append({"name": "Survey", "path": "questionnaire/survey"})

    # Add negative position pages (before End)
    for pos, page in feature_pages:
        if pos < 0:
            # -1 means last, -2 means second to last, etc.
            pages.append(page)

    # Add End page
    pages.append({"name": "End", "path": "end"})

    # Format as TOML
    lines = ["PAGE_LIST = ["]
    for page in pages:
        if "conditional_routing" in page:
            # Format conditional routing block
            lines.append("    {conditional_routing=[")
            for route in page["conditional_routing"]:
                condition = route["condition"]
                route_pages = route["page_list"]
                page_entries = ", ".join(
                    f"{{name='{p['name']}', path='{p['path']}'}}" for p in route_pages
                )
                lines.append(f"        {{condition={condition}, page_list=[{page_entries}]}},")
            lines.append("    ]},")
        else:
            lines.append(f"    {{name='{page['name']}', path='{page['path']}'}},")
    lines.append("]")

    return "\n".join(lines)


def build_config(name: str, title: str, selected_features: list[str],
                 admin_password: str = "admin") -> str:
    """Build the complete TOML configuration file."""
    use_pre_post = "pre_post" in selected_features

    config_lines = [
        "# Database settings",
        f"SQLALCHEMY_DATABASE_URI = 'sqlite:///{escape_toml_string(name)}.db'",
        "",
        "# Security - change this to something unique in production",
        f"SECRET_KEY = '{generate_secret_key()}'",
        "",
        "# Application Settings",
        f"TITLE = '{escape_toml_string(title)}'",
        f"ADMIN_PASSWORD = '{escape_toml_string(admin_password)}'",
        "USE_BREADCRUMBS = true",
        "PORT = 5000",
        "APPLICATION_ROOT = ''",
        "",
        "# Session Settings",
        "RETRIEVE_SESSIONS = true",
        "ALLOW_RETAKES = true",
        "",
        "# Completion Settings",
        "GENERATE_COMPLETION_CODE = true",
        'COMPLETION_CODE_MESSAGE = "Your completion code is:"',
    ]

    # Add feature-specific config lines
    for feature_key in selected_features:
        feature = FEATURES.get(feature_key, {})
        if "config_lines" in feature:
            config_lines.extend(feature["config_lines"])

    # Add page list
    config_lines.append("")
    config_lines.append("# Page List - defines the experiment flow")
    config_lines.append(build_page_list(selected_features, use_pre_post))

    return "\n".join(config_lines)


def build_consent_html(title: str) -> str:
    """Build a basic consent.html file."""
    return f'''<h1>{html.escape(title)}</h1>

<h2>Consent to Participate</h2>

<p>Welcome to this study. Please read the following information carefully before proceeding.</p>

<div>
    <h3>Purpose</h3>
    <p>[Describe the purpose of your study here]</p>

    <h3>Procedures</h3>
    <p>[Describe what participants will be asked to do]</p>

    <h3>Risks and Benefits</h3>
    <p>[Describe any risks and benefits]</p>

    <h3>Confidentiality</h3>
    <p>[Describe how data will be handled]</p>

    <h3>Contact</h3>
    <p>[Provide contact information for questions]</p>
</div>

<p><strong>By clicking "I Agree" below, you indicate that you have read and understood the information above and agree to participate in this study.</strong></p>
'''


def build_survey_json() -> str:
    """Build a basic survey questionnaire JSON file."""
    return '''{
    "title": "Survey",
    "instructions": "Please answer the following questions.",
    "questions": [
        {
            "questiontype": "radiogrid",
            "instructions": "Rate your agreement with the following statements.",
            "id": "agreement",
            "labels": [
                "Strongly disagree",
                "Disagree",
                "Neutral",
                "Agree",
                "Strongly agree"
            ],
            "q_text": [
                {
                    "id": "item1",
                    "text": "Statement 1"
                },
                {
                    "id": "item2",
                    "text": "Statement 2"
                },
                {
                    "id": "item3",
                    "text": "Statement 3"
                }
            ]
        },
        {
            "questiontype": "field",
            "instructions": "Please provide any additional comments.",
            "id": "comments",
            "required": false
        }
    ]
}
'''


def create_project(name: str, title: str, selected_features: list[str],
                   admin_password: str = "admin") -> Path:
    """Create the project directory and files."""
    project_path = Path.cwd() / name

    # Create directories
    project_path.mkdir(exist_ok=False)

    try:
        (project_path / "questionnaires").mkdir()

        # Create config.toml
        config_content = build_config(name, title, selected_features, admin_password)
        (project_path / "config.toml").write_text(config_content, encoding='utf-8')

        # Create consent.html
        consent_content = build_consent_html(title)
        (project_path / "consent.html").write_text(consent_content, encoding='utf-8')

        # Create base survey.json
        survey_content = build_survey_json()
        (project_path / "questionnaires" / "survey.json").write_text(
            survey_content, encoding='utf-8')

        # Create feature-specific files
        for feature_key in selected_features:
            feature = FEATURES.get(feature_key, {})
            if "files" in feature:
                for file_path, content in feature["files"].items():
                    full_path = project_path / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding='utf-8')

    except Exception as e:
        # Clean up on partial failure
        if project_path.exists():
            shutil.rmtree(project_path)
        raise

    return project_path


def print_tree(path: Path, prefix: str = "", is_last: bool = True) -> list[str]:
    """Generate a tree representation of the directory structure."""
    lines = []
    connector = "`-- " if is_last else "|-- "
    lines.append(f"{prefix}{connector}{path.name}")

    if path.is_dir():
        children = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        for i, child in enumerate(children):
            is_child_last = i == len(children) - 1
            extension = "    " if is_last else "|   "
            lines.extend(print_tree(child, prefix + extension, is_child_last))

    return lines


def run_wizard() -> Optional[Path]:
    """Run the interactive project creation wizard."""
    print("\nBOFS Project Initialization Wizard")
    print("=" * 40)
    print()

    # Get project name
    def name_validator(x):
        result = validate_project_name(x)
        return True if result is True else result

    name = questionary.text(
        "Project name (directory name):",
        validate=name_validator
    ).ask()

    if name is None:  # User cancelled
        print("\nCancelled.")
        return None

    # Get project title
    default_title = name.replace("_", " ").replace("-", " ").title()
    title = questionary.text(
        "Project title (displayed to participants):",
        default=default_title
    ).ask()

    if title is None:  # User cancelled
        print("\nCancelled.")
        return None

    # Get admin password
    print("\nNote: The admin password will be stored in plaintext in config.toml")
    admin_password = questionary.password(
        "Admin password (default: admin):",
        default="admin"
    ).ask()

    if admin_password is None:  # User cancelled
        print("\nCancelled.")
        return None

    # Build feature choices
    choices = []
    for key, feature in FEATURES.items():
        choice = questionary.Choice(
            title=f"{feature['label']} - {feature['description']}",
            value=key,
            checked=feature.get("default", False)
        )
        choices.append(choice)

    # Select features
    selected = questionary.checkbox(
        "Select features to include:",
        choices=choices,
        instruction="(Space to select, Enter to confirm)"
    ).ask()

    if selected is None:  # User cancelled
        print("\nCancelled.")
        return None

    # Confirm
    print()
    print(f"Creating project '{name}' with features:")
    if selected:
        for feature_key in selected:
            print(f"  - {FEATURES[feature_key]['label']}")
    else:
        print("  (no optional features)")
    print()

    confirm = questionary.confirm("Proceed with project creation?", default=True).ask()

    if not confirm:
        print("\nCancelled.")
        return None

    # Create the project
    print()
    print("Creating project...")
    try:
        project_path = create_project(name, title, selected, admin_password)
    except FileExistsError:
        print(f"\nError: Directory '{name}' already exists.")
        return None
    except Exception as e:
        print(f"\nError creating project: {e}")
        return None

    # Print success message
    print()
    print(f"Created: {name}/")
    tree_lines = print_tree(project_path)
    for line in tree_lines[1:]:  # Skip the root line (already printed above)
        print(line)

    print()
    print("Next steps:")
    print(f"  cd {name}")
    print("  BOFS config.toml -d")
    print()

    return project_path
