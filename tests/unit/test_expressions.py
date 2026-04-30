"""Tests for the BOFS expression engine (parser + evaluators)."""

import json
import os
import shutil
import subprocess

import pytest

from BOFS.expressions import (
    ExpressionError,
    evaluate,
    parse,
    referenced_fields,
)


# ---------------------------------------------------------------------------
# parse — accepted constructs
# ---------------------------------------------------------------------------

class TestParseAccepts:
    def test_int_literal(self):
        assert parse("42") == {"const": 42}

    def test_float_literal(self):
        assert parse("3.14") == {"const": 3.14}

    def test_string_literal(self):
        assert parse("'hello'") == {"const": "hello"}

    def test_true(self):
        assert parse("True") == {"const": True}

    def test_false(self):
        assert parse("False") == {"const": False}

    def test_none(self):
        assert parse("None") == {"const": None}

    def test_name(self):
        assert parse("age") == {"var": "age"}

    def test_arithmetic(self):
        ast = parse("a + 1")
        assert ast == {"op": "+", "args": [{"var": "a"}, {"const": 1}]}

    def test_floor_div(self):
        assert parse("a // 10")["op"] == "//"

    def test_modulo(self):
        assert parse("a % 3")["op"] == "%"

    def test_unary_minus(self):
        assert parse("-x") == {"op": "neg", "args": [{"var": "x"}]}

    def test_unary_not(self):
        assert parse("not x") == {"op": "not", "args": [{"var": "x"}]}

    def test_comparison(self):
        ast = parse("age >= 18")
        assert ast == {"op": ">=", "args": [{"var": "age"}, {"const": 18}]}

    def test_chained_comparison_flattens_to_and(self):
        ast = parse("0 < x < 10")
        assert ast["op"] == "and"
        assert len(ast["args"]) == 2
        assert ast["args"][0]["op"] == "<"
        assert ast["args"][1]["op"] == "<"

    def test_in_list(self):
        ast = parse("country in ['US', 'CA']")
        assert ast["op"] == "in"
        assert ast["args"][1]["op"] == "list"

    def test_not_in(self):
        assert parse("x not in [1, 2]")["op"] == "not_in"

    def test_logical_and(self):
        ast = parse("a and b and c")
        assert ast == {
            "op": "and",
            "args": [{"var": "a"}, {"var": "b"}, {"var": "c"}],
        }

    def test_logical_or(self):
        assert parse("a or b")["op"] == "or"

    def test_parenthesized(self):
        ast = parse("(a + b) * c")
        assert ast["op"] == "*"
        assert ast["args"][0]["op"] == "+"

    def test_function_call_whitelisted(self):
        ast = parse("mean([q1, q2, q3])")
        assert ast == {
            "call": "mean",
            "args": [{
                "op": "list",
                "args": [{"var": "q1"}, {"var": "q2"}, {"var": "q3"}],
            }],
        }

    def test_if_expression(self):
        ast = parse("a if cond else b")
        assert ast == {
            "op": "if",
            "args": [{"var": "cond"}, {"var": "a"}, {"var": "b"}],
        }

    def test_nested_list_with_expressions(self):
        ast = parse("[q1, 6 - q2, q3]")
        assert ast["op"] == "list"
        assert len(ast["args"]) == 3
        assert ast["args"][1]["op"] == "-"


# ---------------------------------------------------------------------------
# parse — rejected constructs
# ---------------------------------------------------------------------------

class TestParseRejects:
    @pytest.mark.parametrize("src", [
        "self.foo",            # attribute access
        "obj['x']",            # subscript
        "lambda x: x",         # lambda
        "[x for x in xs]",     # list comprehension
        "{1, 2}",              # set literal
        "{'a': 1}",            # dict literal
        "*xs",                 # starred
        "f(x=1)",              # keyword args
        "exec('x')",           # disallowed func
        "__import__('os')",    # disallowed func
        "open('f')",           # disallowed func
    ])
    def test_disallowed_construct(self, src):
        with pytest.raises(ExpressionError):
            parse(src)

    def test_syntax_error(self):
        with pytest.raises(ExpressionError):
            parse("a +")

    def test_empty(self):
        with pytest.raises(ExpressionError):
            parse("")

    def test_whitespace_only(self):
        with pytest.raises(ExpressionError):
            parse("   ")

    def test_non_string(self):
        with pytest.raises(ExpressionError):
            parse(42)


# ---------------------------------------------------------------------------
# referenced_fields
# ---------------------------------------------------------------------------

class TestReferencedFields:
    def test_simple(self):
        assert referenced_fields(parse("age")) == {"age"}

    def test_arithmetic(self):
        assert referenced_fields(parse("a + b * c")) == {"a", "b", "c"}

    def test_function_call_does_not_include_func_name(self):
        ast = parse("mean([q1, q2])")
        assert referenced_fields(ast) == {"q1", "q2"}

    def test_compound_predicate(self):
        ast = parse("age < 18 and country in ['US', 'CA']")
        assert referenced_fields(ast) == {"age", "country"}

    def test_constant_only(self):
        assert referenced_fields(parse("42")) == set()


# ---------------------------------------------------------------------------
# Python evaluator
# ---------------------------------------------------------------------------

# Minimal function set for tests that don't want to import BOFS.util.
_TEST_FUNCS = {
    "len": len, "min": min, "max": max, "sum": sum, "abs": abs,
    "round": round, "int": int, "float": float, "str": str, "bool": bool,
    "mean": lambda xs: sum(xs) / len(xs),
    "median": lambda xs: sorted(xs)[len(xs) // 2],
    "stdev": lambda xs: 0.0, "std": lambda xs: 0.0,
    "var": lambda xs: 0.0, "variance": lambda xs: 0.0,
}


def py_eval(src, env):
    return evaluate(parse(src), env, functions=_TEST_FUNCS)


class TestPythonEvaluator:
    def test_arithmetic(self):
        assert py_eval("a + b * c", {"a": 1, "b": 2, "c": 3}) == 7

    def test_floor_div_negative(self):
        # Python semantics: -7 // 2 == -4 (not -3 like JS Math.trunc).
        assert py_eval("a // b", {"a": -7, "b": 2}) == -4

    def test_modulo_negative(self):
        # Python semantics: -7 % 2 == 1 (sign of divisor).
        assert py_eval("a % b", {"a": -7, "b": 2}) == 1

    def test_comparison(self):
        assert py_eval("age >= 18", {"age": 18}) is True
        assert py_eval("age >= 18", {"age": 17}) is False

    def test_chained_comparison(self):
        assert py_eval("0 < x < 10", {"x": 5}) is True
        assert py_eval("0 < x < 10", {"x": 10}) is False

    def test_in_list(self):
        assert py_eval("c in ['US', 'CA']", {"c": "US"}) is True
        assert py_eval("c in ['US', 'CA']", {"c": "MX"}) is False

    def test_in_string(self):
        assert py_eval("'foo' in s", {"s": "foobar"}) is True

    def test_not_in(self):
        assert py_eval("c not in [1, 2]", {"c": 3}) is True

    def test_and_short_circuits(self):
        # Right side would raise (undefined var), but short-circuit prevents it.
        assert py_eval("flag and missing", {"flag": False}) is False

    def test_or_short_circuits(self):
        assert py_eval("flag or missing", {"flag": True}) is True

    def test_if_expression(self):
        assert py_eval("a if cond else b", {"cond": True, "a": 1, "b": 2}) == 1
        assert py_eval("a if cond else b", {"cond": False, "a": 1, "b": 2}) == 2

    def test_function_mean(self):
        assert py_eval("mean([1, 2, 3])", {}) == 2.0

    def test_compound_predicate(self):
        env = {"age": 17, "country": "US"}
        assert py_eval(
            "age < 18 and country in ['US', 'CA']", env
        ) is True

    def test_undefined_var_raises(self):
        with pytest.raises(ExpressionError):
            py_eval("missing", {})

    def test_disallowed_function_raises(self):
        # The parser rejects this, but if a malformed AST is supplied directly,
        # the evaluator must also refuse.
        bad_ast = {"call": "exec", "args": []}
        with pytest.raises(ExpressionError):
            evaluate(bad_ast, {}, functions=_TEST_FUNCS)


# ---------------------------------------------------------------------------
# Parity: same AST + same env should yield the same value in Python and JS.
# Run via Node if available; skip cleanly otherwise.
# ---------------------------------------------------------------------------

PARITY_CASES = [
    # (expression, env)
    ("a + b * c",                     {"a": 1, "b": 2, "c": 3}),
    ("(a + b) * c",                   {"a": 1, "b": 2, "c": 3}),
    ("a - b - c",                     {"a": 10, "b": 3, "c": 2}),
    ("a // b",                        {"a": 7, "b": 2}),
    ("a % b",                         {"a": 7, "b": 3}),
    ("age < 18",                      {"age": 17}),
    ("age >= 18",                     {"age": 18}),
    ("0 < x < 10",                    {"x": 5}),
    ("country in ['US', 'CA']",       {"country": "US"}),
    ("country not in ['US', 'CA']",   {"country": "MX"}),
    ("'foo' in s",                    {"s": "foobar"}),
    ("a and b",                       {"a": True, "b": False}),
    ("a or b",                        {"a": False, "b": 7}),
    ("not x",                         {"x": 0}),
    ("not x",                         {"x": ""}),
    ("a if cond else b",              {"cond": True, "a": 1, "b": 2}),
    ("mean([1, 2, 3, 4])",            {}),
    ("min(a, b, c)",                  {"a": 5, "b": 2, "c": 9}),
    ("max([1, 9, 3])",                {}),
    ("len(s)",                        {"s": "hello"}),
    ("abs(x)",                        {"x": -7}),
    ("round(x, 2)",                   {"x": 3.14159}),
    ("age < 18 and country in ['US', 'CA']", {"age": 17, "country": "US"}),
    ("score >= 50 or override",       {"score": 30, "override": True}),
]


def _node_available():
    return shutil.which("node") is not None


def _js_eval_via_node(ast, env):
    """Evaluate `ast` against `env` via a Node subprocess; return the JSON value."""
    js_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "BOFS", "static", "js",
        "bofs_expressions.js"
    ))
    payload = json.dumps({"ast": ast, "env": env})
    script = (
        "var BOFSExpr = require(" + json.dumps(js_path) + ");"
        "var input = JSON.parse(process.argv[1]);"
        "var out = BOFSExpr.evaluate(input.ast, input.env);"
        "process.stdout.write(JSON.stringify(out));"
    )
    result = subprocess.run(
        ["node", "-e", script, payload],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(not _node_available(), reason="node is not installed")
@pytest.mark.parametrize("src,env", PARITY_CASES)
def test_python_js_parity(src, env):
    ast = parse(src)
    py_val = evaluate(ast, env, functions=_TEST_FUNCS)
    js_val = _js_eval_via_node(ast, env)
    # JSON round-trip: Python booleans serialize as JSON true/false and come
    # back as Python True/False, so direct equality works.
    assert py_val == js_val, (
        f"parity mismatch for {src!r} with env {env!r}: "
        f"py={py_val!r}, js={js_val!r}"
    )
