"""Tests for BOFS/sanitizer.py — researcher-HTML allowlist."""

from BOFS.sanitizer import sanitize_html, sanitize_questionnaire_json


# ---------------------------------------------------------------------------
# sanitize_html
# ---------------------------------------------------------------------------

def test_strips_script_tag():
    out = sanitize_html("hello<script>alert(1)</script>world")
    assert "<script>" not in out
    assert "alert(1)" not in out
    assert "hello" in out and "world" in out


def test_strips_event_handlers():
    out = sanitize_html('<a href="/x" onclick="evil()">click</a>')
    assert "onclick" not in out
    assert 'href="/x"' in out


def test_strips_javascript_url():
    out = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in out


def test_keeps_basic_formatting():
    text = "<b>bold</b> <i>italic</i> <u>underline</u>"
    assert sanitize_html(text) == text


def test_keeps_lists_and_headings():
    text = "<h2>Title</h2><ul><li>one</li><li>two</li></ul>"
    assert sanitize_html(text) == text


def test_keeps_video_tag_with_attrs():
    text = '<video src="/v.mp4" controls width="320"></video>'
    out = sanitize_html(text)
    assert "<video" in out
    assert "controls" in out
    assert 'src="/v.mp4"' in out


def test_keeps_audio_tag():
    text = '<audio src="/a.mp3" controls autoplay></audio>'
    out = sanitize_html(text)
    assert "<audio" in out
    assert "autoplay" in out


def test_keeps_img_with_alt():
    text = '<img src="/p.png" alt="diagram" width="200">'
    out = sanitize_html(text)
    assert "<img" in out
    assert 'alt="diagram"' in out


def test_strips_iframe():
    out = sanitize_html('<iframe src="https://attacker"></iframe>')
    assert "<iframe" not in out


def test_strips_style_attribute():
    out = sanitize_html('<p style="background:url(javascript:alert(1))">x</p>')
    assert "style=" not in out


def test_strips_data_url_in_img():
    out = sanitize_html('<img src="data:text/html,<script>alert(1)</script>">')
    # data: scheme must be removed; the text content of the script must not survive
    assert "data:" not in out
    assert "<script" not in out


def test_passes_non_string_through():
    assert sanitize_html(None) is None
    assert sanitize_html(42) == 42
    assert sanitize_html(True) is True


# ---------------------------------------------------------------------------
# sanitize_questionnaire_json
# ---------------------------------------------------------------------------

def test_sanitizes_top_level_instructions():
    data = {"instructions": "<b>ok</b><script>bad</script>"}
    sanitize_questionnaire_json(data)
    assert "<script>" not in data["instructions"]
    assert "<b>ok</b>" in data["instructions"]


def test_sanitizes_question_fields():
    data = {
        "questions": [
            {
                "id": "q1",
                "title": "<i>title</i><script>x</script>",
                "instructions": "<u>do this</u><img src=x onerror=alert(1)>",
                "text": "<b>bold</b>",
            }
        ]
    }
    sanitize_questionnaire_json(data)
    q = data["questions"][0]
    assert "<script>" not in q["title"]
    assert "<i>title</i>" in q["title"]
    assert "onerror" not in q["instructions"]
    assert q["text"] == "<b>bold</b>"


def test_sanitizes_grid_subquestions():
    data = {
        "questions": [
            {
                "id": "grid",
                "questiontype": "radiogrid",
                "questions": [
                    {"id": "row1", "text": "<b>row 1</b><script>evil()</script>"},
                    {"id": "row2", "text": "row 2"},
                ],
            }
        ]
    }
    sanitize_questionnaire_json(data)
    rows = data["questions"][0]["questions"]
    assert "<script>" not in rows[0]["text"]
    assert "<b>row 1</b>" in rows[0]["text"]
    assert rows[1]["text"] == "row 2"


def test_does_not_touch_q_code():
    """The intentional code-injection slot is left alone so researchers can
    embed task-specific JS."""
    data = {
        "code": "<script>setupTask()</script>",
        "questions": [],
    }
    sanitize_questionnaire_json(data)
    assert data["code"] == "<script>setupTask()</script>"


def test_idempotent():
    data = {"instructions": "<b>ok</b>"}
    sanitize_questionnaire_json(data)
    sanitize_questionnaire_json(data)
    assert data["instructions"] == "<b>ok</b>"


def test_handles_missing_questions_key():
    data = {"instructions": "<b>ok</b>"}
    out = sanitize_questionnaire_json(data)
    assert out is data
    assert data["instructions"] == "<b>ok</b>"


def test_handles_non_dict():
    # Defensive: caller-shaped data that isn't a dict shouldn't crash.
    assert sanitize_questionnaire_json([]) == []
    assert sanitize_questionnaire_json(None) is None
