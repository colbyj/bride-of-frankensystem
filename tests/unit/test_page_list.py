"""
Comprehensive tests for the PageList class from BOFS/PageList.py.

Only pure methods that do not require Flask context are tested here.
Methods that depend on Flask request/session (get_index, next_path,
previous_path, get_questionnaire_list) are excluded.

flat_page_list is tested ONLY when called with an explicit ``condition``
keyword argument (bypassing the Flask-dependent default path).
"""

import sys
import types
import importlib
from unittest.mock import MagicMock
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import PageList while bypassing the heavy BOFS __init__.py imports.
#
# BOFS/__init__.py pulls in BOFSFlask, globals, and JSONQuestionnaire which
# all depend on Flask application/request context at import time.  PageList
# itself only references ``BOFS.util`` (for fetch_current_condition /
# fetch_condition_count) and ``flask`` (for current_app and request), none
# of which are needed by the pure methods under test.
#
# Strategy: pre-populate sys.modules with lightweight stubs for BOFS and
# BOFS.util so that ``from BOFS import util`` inside PageList.py resolves
# without triggering the real __init__.py import chain.
# ---------------------------------------------------------------------------

# Ensure the project root is on sys.path so ``BOFS`` is discoverable.
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Create a minimal stand-in for the BOFS package if it hasn't been imported yet.
if 'BOFS' not in sys.modules:
    _bofs_stub = types.ModuleType('BOFS')
    _bofs_stub.__path__ = [str(Path(_project_root) / 'BOFS')]
    _bofs_stub.__package__ = 'BOFS'
    sys.modules['BOFS'] = _bofs_stub

# Create a stub for BOFS.util with the functions PageList references.
if 'BOFS.util' not in sys.modules:
    _util_stub = types.ModuleType('BOFS.util')
    _util_stub.fetch_current_condition = MagicMock(return_value=1)
    _util_stub.fetch_condition_count = MagicMock(return_value=2)
    sys.modules['BOFS.util'] = _util_stub
    sys.modules['BOFS'].util = _util_stub

# Now import PageList — it will find BOFS and BOFS.util already in sys.modules.
from BOFS.PageList import PageList


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

def test_init_stores_page_list(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    assert pl.page_list is simple_page_list_data


def test_init_empty_page_list():
    pl = PageList([])
    assert pl.page_list == []


def test_init_page_list_not_shared_between_instances(simple_page_list_data):
    """Each instance should hold its own reference, not share a class-level list."""
    pl1 = PageList(simple_page_list_data)
    pl2 = PageList([{'name': 'Other', 'path': 'other'}])
    assert pl1.page_list is not pl2.page_list
    assert len(pl1.page_list) == 4
    assert len(pl2.page_list) == 1


# ---------------------------------------------------------------------------
# unconditional_pages
# ---------------------------------------------------------------------------

def test_unconditional_simple_list_returns_all(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    result = pl.unconditional_pages()
    assert result == simple_page_list_data


def test_unconditional_excludes_cr_blocks(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    result = pl.unconditional_pages()
    names = [p['name'] for p in result]
    assert names == ['Consent', 'Pre Survey', 'Post Survey', 'End']
    for entry in result:
        assert 'conditional_routing' not in entry


def test_unconditional_empty_page_list():
    pl = PageList([])
    assert pl.unconditional_pages() == []


def test_unconditional_only_cr_entries():
    """If every entry is a conditional_routing block, result is empty."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A', 'path': 'a'}]}
        ]}
    ]
    pl = PageList(data)
    assert pl.unconditional_pages() == []


def test_unconditional_returns_new_list(simple_page_list_data):
    """Each call returns a new list object, not the internal page_list."""
    pl = PageList(simple_page_list_data)
    r1 = pl.unconditional_pages()
    r2 = pl.unconditional_pages()
    assert r1 == r2
    assert r1 is not r2


# ---------------------------------------------------------------------------
# conditional_pages
# ---------------------------------------------------------------------------

def test_conditional_pages_condition_1(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    result = pl.conditional_pages(1)
    assert len(result) == 2
    assert result[0]['name'] == 'Control Task'
    assert result[1]['name'] == 'Control Follow-up'


def test_conditional_pages_condition_2(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    result = pl.conditional_pages(2)
    assert len(result) == 1
    assert result[0]['name'] == 'Treatment Task'


def test_conditional_pages_nonexistent_condition(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    assert pl.conditional_pages(99) == []


def test_conditional_pages_simple_list_returns_empty(simple_page_list_data):
    """No conditional_routing blocks means nothing to return."""
    pl = PageList(simple_page_list_data)
    assert pl.conditional_pages(1) == []


def test_conditional_pages_empty_page_list():
    pl = PageList([])
    assert pl.conditional_pages(1) == []


def test_conditional_pages_multiple_cr_blocks():
    """Pages from all conditional_routing blocks for the same condition are collected."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A', 'path': 'a'}]},
            {'condition': 2, 'page_list': [{'name': 'B', 'path': 'b'}]},
        ]},
        {'name': 'Middle', 'path': 'middle'},
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'C', 'path': 'c'}]},
            {'condition': 2, 'page_list': [{'name': 'D', 'path': 'd'}]},
        ]},
    ]
    pl = PageList(data)
    assert [p['name'] for p in pl.conditional_pages(1)] == ['A', 'C']
    assert [p['name'] for p in pl.conditional_pages(2)] == ['B', 'D']


def test_conditional_pages_empty_condition_page_list():
    """A condition that maps to an empty page_list returns nothing."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': []},
            {'condition': 2, 'page_list': [{'name': 'X', 'path': 'x'}]},
        ]}
    ]
    pl = PageList(data)
    assert pl.conditional_pages(1) == []
    assert len(pl.conditional_pages(2)) == 1


def test_conditional_pages_returns_new_list(conditional_page_list_data):
    """Each call returns a fresh list."""
    pl = PageList(conditional_page_list_data)
    r1 = pl.conditional_pages(1)
    r2 = pl.conditional_pages(1)
    assert r1 == r2
    assert r1 is not r2


# ---------------------------------------------------------------------------
# extract_questionnaire_from_path (static method)
#
# NOTE: This method has a known bug. When include_tag is False it computes
# ``questionnaire_name`` (the portion before the first slash) but then
# returns the *full* stripped path (the local ``questionnaire``) instead of
# ``questionnaire_name``.  Tests below document the ACTUAL buggy behavior.
# ---------------------------------------------------------------------------

def test_extract_simple_path_include_tag_true():
    result = PageList.extract_questionnaire_from_path(
        "questionnaire/example", include_tag=True
    )
    assert result == "example"


def test_extract_simple_path_include_tag_false():
    # With no tag component, the bug is invisible because questionnaire == questionnaire_name.
    result = PageList.extract_questionnaire_from_path(
        "questionnaire/example", include_tag=False
    )
    assert result == "example"


def test_extract_tagged_path_include_tag_true():
    result = PageList.extract_questionnaire_from_path(
        "questionnaire/example/tag1", include_tag=True
    )
    assert result == "example/tag1"


def test_extract_tagged_path_include_tag_false():
    """With include_tag=False, should return just the questionnaire name without the tag."""
    result = PageList.extract_questionnaire_from_path(
        "questionnaire/example/tag1", include_tag=False
    )
    assert result == "example"


def test_extract_default_include_tag_is_false():
    """Default value of include_tag is False."""
    result = PageList.extract_questionnaire_from_path("questionnaire/demo")
    assert result == "demo"


def test_extract_path_without_questionnaire_prefix():
    """If path doesn't start with 'questionnaire/', nothing is stripped."""
    result = PageList.extract_questionnaire_from_path("consent")
    assert result == "consent"


def test_extract_deeply_nested_path_include_tag_false():
    """With include_tag=False and a deep path, should return just the first segment."""
    result = PageList.extract_questionnaire_from_path(
        "questionnaire/deep/nested/path", include_tag=False
    )
    assert result == "deep"


def test_extract_deeply_nested_path_include_tag_true():
    result = PageList.extract_questionnaire_from_path(
        "questionnaire/deep/nested/path", include_tag=True
    )
    assert result == "deep/nested/path"


def test_extract_only_prefix():
    """Edge case: path is exactly 'questionnaire/' with nothing after."""
    result = PageList.extract_questionnaire_from_path("questionnaire/")
    assert result == ""


def test_extract_empty_string():
    """Edge case: empty string path."""
    result = PageList.extract_questionnaire_from_path("")
    assert result == ""


# ---------------------------------------------------------------------------
# flat_page_list (with explicit condition argument only)
# ---------------------------------------------------------------------------

def test_flat_simple_list_any_condition(simple_page_list_data):
    """With no conditional_routing, condition value doesn't matter."""
    pl = PageList(simple_page_list_data)
    result = pl.flat_page_list(condition=1)
    assert result == simple_page_list_data


def test_flat_condition_1(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    result = pl.flat_page_list(condition=1)
    paths = [p['path'] for p in result]
    assert paths == [
        'consent',
        'questionnaire/pre/before',
        'questionnaire/control_q',
        'questionnaire/control_followup',
        'questionnaire/post',
        'end',
    ]


def test_flat_condition_2(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    result = pl.flat_page_list(condition=2)
    paths = [p['path'] for p in result]
    assert paths == [
        'consent',
        'questionnaire/pre/before',
        'questionnaire/treatment_q',
        'questionnaire/post',
        'end',
    ]


def test_flat_condition_0_gets_first_branch(conditional_page_list_data):
    """Condition 0 is special: it matches the first conditional_route because
    of the ``condition == 0`` check in the code."""
    pl = PageList(conditional_page_list_data)
    result = pl.flat_page_list(condition=0)
    paths = [p['path'] for p in result]
    # condition==0 matches the first branch (condition 1's pages)
    assert 'questionnaire/control_q' in paths
    assert 'questionnaire/control_followup' in paths


def test_flat_unmatched_condition_skips_cr_block(conditional_page_list_data):
    """If no conditional_route matches, the CR block contributes nothing."""
    pl = PageList(conditional_page_list_data)
    result = pl.flat_page_list(condition=99)
    paths = [p['path'] for p in result]
    assert paths == [
        'consent',
        'questionnaire/pre/before',
        'questionnaire/post',
        'end',
    ]


def test_flat_empty_page_list():
    pl = PageList([])
    assert pl.flat_page_list(condition=1) == []


def test_flat_returns_new_list_each_call(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    list1 = pl.flat_page_list(condition=1)
    list2 = pl.flat_page_list(condition=1)
    assert list1 == list2
    assert list1 is not list2


def test_flat_multiple_cr_blocks():
    """Multiple conditional_routing blocks are each expanded correctly."""
    data = [
        {'name': 'Start', 'path': 'start'},
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A1', 'path': 'a1'}]},
            {'condition': 2, 'page_list': [{'name': 'A2', 'path': 'a2'}]},
        ]},
        {'name': 'Middle', 'path': 'middle'},
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'B1', 'path': 'b1'}]},
            {'condition': 2, 'page_list': [{'name': 'B2', 'path': 'b2'}]},
        ]},
        {'name': 'End', 'path': 'end'},
    ]
    pl = PageList(data)
    assert [p['path'] for p in pl.flat_page_list(condition=1)] == [
        'start', 'a1', 'middle', 'b1', 'end',
    ]
    assert [p['path'] for p in pl.flat_page_list(condition=2)] == [
        'start', 'a2', 'middle', 'b2', 'end',
    ]


def test_flat_condition_0_with_simple_list(simple_page_list_data):
    """Condition 0 on a list with no CR blocks returns everything unchanged."""
    pl = PageList(simple_page_list_data)
    result = pl.flat_page_list(condition=0)
    assert result == simple_page_list_data


def test_flat_preserves_entry_order(conditional_page_list_data):
    """Unconditional entries before and after the CR block keep their order."""
    pl = PageList(conditional_page_list_data)
    result = pl.flat_page_list(condition=1)
    assert result[0]['path'] == 'consent'
    assert result[-1]['path'] == 'end'


# ---------------------------------------------------------------------------
# parse_list_into_procedure
# ---------------------------------------------------------------------------

def test_procedure_simple_list(simple_page_list_data):
    """Without conditional routing, procedure is the same as page_list."""
    pl = PageList(simple_page_list_data)
    procedure = pl.parse_list_into_procedure()
    assert procedure == simple_page_list_data


def test_procedure_conditional_structure(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    procedure = pl.parse_list_into_procedure()

    # Unconditional entries are plain dicts with 'path'
    assert procedure[0] == {'name': 'Consent', 'path': 'consent'}
    assert procedure[1] == {'name': 'Pre Survey', 'path': 'questionnaire/pre/before'}

    # First CR slot (index 2): both conditions have a page
    cr_slot_0 = procedure[2]
    assert isinstance(cr_slot_0, dict)
    assert cr_slot_0[1] == {'name': 'Control Task', 'path': 'questionnaire/control_q'}
    assert cr_slot_0[2] == {'name': 'Treatment Task', 'path': 'questionnaire/treatment_q'}

    # Second CR slot (index 3): condition 1 has a page, condition 2 is None
    cr_slot_1 = procedure[3]
    assert isinstance(cr_slot_1, dict)
    assert cr_slot_1[1] == {'name': 'Control Follow-up', 'path': 'questionnaire/control_followup'}
    assert cr_slot_1[2] is None

    # Remaining unconditional entries
    assert procedure[4] == {'name': 'Post Survey', 'path': 'questionnaire/post'}
    assert procedure[5] == {'name': 'End', 'path': 'end'}


def test_procedure_length(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    procedure = pl.parse_list_into_procedure()
    # consent + pre + 2 CR slots + post + end = 6
    assert len(procedure) == 6


def test_procedure_empty_page_list():
    pl = PageList([])
    assert pl.parse_list_into_procedure() == []


def test_procedure_equal_length_conditions():
    """When all conditions have the same number of pages, no None padding."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [
                {'name': 'A', 'path': 'a'},
                {'name': 'B', 'path': 'b'},
            ]},
            {'condition': 2, 'page_list': [
                {'name': 'C', 'path': 'c'},
                {'name': 'D', 'path': 'd'},
            ]},
        ]}
    ]
    pl = PageList(data)
    procedure = pl.parse_list_into_procedure()
    assert len(procedure) == 2
    assert procedure[0][1] == {'name': 'A', 'path': 'a'}
    assert procedure[0][2] == {'name': 'C', 'path': 'c'}
    assert procedure[1][1] == {'name': 'B', 'path': 'b'}
    assert procedure[1][2] == {'name': 'D', 'path': 'd'}


def test_procedure_shorter_condition_gets_none_padding():
    """When one condition has fewer pages, extra slots are filled with None."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [
                {'name': 'A', 'path': 'a'},
                {'name': 'B', 'path': 'b'},
                {'name': 'C', 'path': 'c'},
            ]},
            {'condition': 2, 'page_list': [
                {'name': 'X', 'path': 'x'},
            ]},
        ]}
    ]
    pl = PageList(data)
    procedure = pl.parse_list_into_procedure()
    assert len(procedure) == 3
    assert procedure[0][1] == {'name': 'A', 'path': 'a'}
    assert procedure[0][2] == {'name': 'X', 'path': 'x'}
    assert procedure[1][1] == {'name': 'B', 'path': 'b'}
    assert procedure[1][2] is None
    assert procedure[2][1] == {'name': 'C', 'path': 'c'}
    assert procedure[2][2] is None


def test_procedure_three_conditions():
    """Works with more than 2 conditions."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A', 'path': 'a'}]},
            {'condition': 2, 'page_list': [{'name': 'B', 'path': 'b'}]},
            {'condition': 3, 'page_list': [{'name': 'C', 'path': 'c'}]},
        ]}
    ]
    pl = PageList(data)
    procedure = pl.parse_list_into_procedure()
    assert len(procedure) == 1
    assert procedure[0][1] == {'name': 'A', 'path': 'a'}
    assert procedure[0][2] == {'name': 'B', 'path': 'b'}
    assert procedure[0][3] == {'name': 'C', 'path': 'c'}


def test_procedure_only_conditional_entries():
    """Page list with nothing but a CR block."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A', 'path': 'a'}]},
        ]}
    ]
    pl = PageList(data)
    procedure = pl.parse_list_into_procedure()
    assert len(procedure) == 1
    assert procedure[0][1] == {'name': 'A', 'path': 'a'}


def test_procedure_empty_condition_page_lists():
    """All conditions have empty page lists -> no CR slots emitted."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': []},
            {'condition': 2, 'page_list': []},
        ]}
    ]
    pl = PageList(data)
    assert pl.parse_list_into_procedure() == []


def test_procedure_cr_keys_are_condition_numbers(conditional_page_list_data):
    """The dict keys in CR slots should be the integer condition numbers."""
    pl = PageList(conditional_page_list_data)
    procedure = pl.parse_list_into_procedure()
    cr_slot = procedure[2]
    assert set(cr_slot.keys()) == {1, 2}


def test_procedure_multiple_cr_blocks():
    """Multiple CR blocks are each expanded into interleaved slots."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A', 'path': 'a'}]},
            {'condition': 2, 'page_list': [{'name': 'B', 'path': 'b'}]},
        ]},
        {'name': 'Mid', 'path': 'mid'},
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'C', 'path': 'c'}]},
            {'condition': 2, 'page_list': [{'name': 'D', 'path': 'd'}]},
        ]},
    ]
    pl = PageList(data)
    procedure = pl.parse_list_into_procedure()
    assert len(procedure) == 3  # cr_slot_1 + mid + cr_slot_2
    assert procedure[0][1] == {'name': 'A', 'path': 'a'}
    assert procedure[0][2] == {'name': 'B', 'path': 'b'}
    assert procedure[1] == {'name': 'Mid', 'path': 'mid'}
    assert procedure[2][1] == {'name': 'C', 'path': 'c'}
    assert procedure[2][2] == {'name': 'D', 'path': 'd'}


# ---------------------------------------------------------------------------
# to_mermaid
# ---------------------------------------------------------------------------

def test_mermaid_starts_with_flowchart(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    assert output.startswith("flowchart TB\n")


def test_mermaid_contains_all_page_names(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    assert "Consent" in output
    assert "Survey" in output
    assert "End" in output


def test_mermaid_contains_arrows(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    assert "-->" in output


def test_mermaid_strips_questionnaire_prefix(simple_page_list_data):
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    # Paths like "questionnaire/example" should appear as "example"
    assert "example" in output
    assert "example_grid" in output


def test_mermaid_merges_same_name_entries(simple_page_list_data):
    """Adjacent entries with the same name should merge their paths into
    one node using <br> separators."""
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    # Both questionnaire/example and questionnaire/example_grid have
    # name "Survey", so they should be merged into one node.
    assert "<br>example<br>example_grid" in output


def test_mermaid_conditional_output(conditional_page_list_data):
    pl = PageList(conditional_page_list_data)
    output = pl.to_mermaid()
    assert output.startswith("flowchart TB\n")
    assert "control_q" in output
    assert "treatment_q" in output


def test_mermaid_conditional_branch_connector(conditional_page_list_data):
    """Conditional branches reconnect with ' & ' join syntax in Mermaid."""
    pl = PageList(conditional_page_list_data)
    output = pl.to_mermaid()
    assert " & " in output


def test_mermaid_empty_page_list():
    pl = PageList([])
    output = pl.to_mermaid()
    assert output == "flowchart TB\n"


def test_mermaid_single_page():
    data = [{'name': 'Only', 'path': 'only_page'}]
    pl = PageList(data)
    output = pl.to_mermaid()
    assert "flowchart TB\n" in output
    assert "Only" in output
    assert "only_page" in output
    # Single page should have no arrows
    assert "-->" not in output


def test_mermaid_bold_header_format(simple_page_list_data):
    """Each node should have its header wrapped in <b> tags."""
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    assert "<b>Consent</b>" in output
    assert "<b>End</b>" in output


def test_mermaid_node_parentheses_format(simple_page_list_data):
    """Node definitions use parentheses with quoted content."""
    pl = PageList(simple_page_list_data)
    output = pl.to_mermaid()
    # Nodes are formatted as: name("content")
    assert '("' in output
    assert '")' in output


def test_mermaid_two_pages_arrow():
    data = [
        {'name': 'First', 'path': 'first'},
        {'name': 'Second', 'path': 'second'},
    ]
    pl = PageList(data)
    output = pl.to_mermaid()
    assert "-->" in output
    assert "First" in output
    assert "Second" in output


def test_mermaid_conditional_only():
    """A page list that is entirely a conditional_routing block should produce valid output."""
    data = [
        {'conditional_routing': [
            {'condition': 1, 'page_list': [{'name': 'A', 'path': 'a'}]},
            {'condition': 2, 'page_list': [{'name': 'B', 'path': 'b'}]},
        ]}
    ]
    pl = PageList(data)
    output = pl.to_mermaid()
    assert output.startswith("flowchart TB\n")
    assert "A" in output
    assert "B" in output


# ---------------------------------------------------------------------------
# show_if — page-level conditional skipping
# ---------------------------------------------------------------------------

class TestShowIfCompilation:
    def test_show_if_attaches_ast(self):
        data = [
            {'name': 'A', 'path': 'a'},
            {'name': 'B', 'path': 'b', 'show_if': 'age < 18'},
            {'name': 'C', 'path': 'c'},
        ]
        pl = PageList(data)
        assert '_show_if_ast' in data[1]
        ast = data[1]['_show_if_ast']
        assert ast == {'op': '<', 'args': [{'var': 'age'}, {'const': 18}]}
        assert '_show_if_ast' not in data[0]
        assert '_show_if_ast' not in data[2]

    def test_show_if_in_conditional_routing(self):
        data = [
            {'conditional_routing': [
                {'condition': 1, 'page_list': [
                    {'name': 'X', 'path': 'x', 'show_if': 'flag == True'},
                ]},
            ]},
        ]
        PageList(data)
        nested = data[0]['conditional_routing'][0]['page_list'][0]
        assert '_show_if_ast' in nested

    def test_show_if_two_part_reference(self):
        data = [
            {'name': 'X', 'path': 'x', 'show_if': 'demographics.age >= 18'},
        ]
        PageList(data)
        ast = data[0]['_show_if_ast']
        refs = data[0]['_show_if_refs']
        # The dotted reference is replaced with a placeholder var; the
        # side table records what the placeholder resolves to.
        placeholder = ast['args'][0]['var']
        assert placeholder.startswith('_bofs_ref_')
        assert refs[placeholder] == {
            'qname': 'demographics',
            'tag': None,
            'field': 'age',
            'source': 'demographics.age',
        }

    def test_show_if_three_part_reference_with_tag(self):
        data = [
            {'name': 'X', 'path': 'x',
             'show_if': 'survey.before.q1 == 1'},
        ]
        PageList(data)
        ast = data[0]['_show_if_ast']
        refs = data[0]['_show_if_refs']
        placeholder = ast['args'][0]['var']
        assert refs[placeholder] == {
            'qname': 'survey',
            'tag': 'before',
            'field': 'q1',
            'source': 'survey.before.q1',
        }

    def test_show_if_explicit_empty_tag(self):
        data = [
            {'name': 'X', 'path': 'x', 'show_if': 'survey..q1 > 0'},
        ]
        PageList(data)
        refs = data[0]['_show_if_refs']
        spec = next(iter(refs.values()))
        assert spec['qname'] == 'survey'
        assert spec['tag'] == ''
        assert spec['field'] == 'q1'

    def test_show_if_multiple_tagged_references(self):
        data = [
            {'name': 'X', 'path': 'x',
             'show_if': 'survey.before.q1 < survey.after.q1'},
        ]
        PageList(data)
        refs = data[0]['_show_if_refs']
        # Two distinct placeholders, one per dotted reference.
        assert len(refs) == 2
        tags = {spec['tag'] for spec in refs.values()}
        assert tags == {'before', 'after'}

    def test_show_if_does_not_eat_float_literals(self):
        data = [
            {'name': 'X', 'path': 'x', 'show_if': 'score > 3.5'},
        ]
        PageList(data)
        # 3.5 must NOT be picked up as a dotted reference.
        refs = data[0]['_show_if_refs']
        assert refs == {}

    def test_show_if_unparseable_raises(self):
        data = [{'name': 'X', 'path': 'x', 'show_if': 'age <'}]
        with pytest.raises(Exception, match="show_if"):
            PageList(data)

    def test_show_if_disallowed_construct_raises(self):
        data = [{'name': 'X', 'path': 'x', 'show_if': '__import__("os")'}]
        with pytest.raises(Exception, match="show_if"):
            PageList(data)

    def test_show_if_non_string_raises(self):
        data = [{'name': 'X', 'path': 'x', 'show_if': 42}]
        with pytest.raises(Exception, match="show_if"):
            PageList(data)


class TestFlatPageListShowIf:
    def test_no_participant_id_keeps_all_pages(self):
        data = [
            {'name': 'A', 'path': 'a'},
            {'name': 'B', 'path': 'b', 'show_if': 'age < 18'},
            {'name': 'C', 'path': 'c'},
        ]
        pl = PageList(data)
        # No participant context — show_if cannot be evaluated, so the
        # page is kept by default.
        result = pl.flat_page_list(condition=1)
        assert [p['name'] for p in result] == ['A', 'B', 'C']

    def test_show_if_filters_when_predicate_false(self, monkeypatch):
        # Patch _page_visible directly to simulate predicate evaluation
        # without standing up a Flask app + DB.
        from BOFS import PageList as plmod

        data = [
            {'name': 'A', 'path': 'a'},
            {'name': 'B', 'path': 'b', 'show_if': 'age < 18'},
            {'name': 'C', 'path': 'c'},
        ]
        pl = plmod.PageList(data)

        def fake_visible(entry, participant_id):
            ast = entry.get('_show_if_ast')
            if ast is None or participant_id is None:
                return True
            # Pretend the participant is 30 — so age < 18 is false.
            return False

        monkeypatch.setattr(plmod.PageList, '_page_visible',
                            staticmethod(fake_visible))
        result = pl.flat_page_list(condition=1, participant_id=42)
        assert [p['name'] for p in result] == ['A', 'C']
