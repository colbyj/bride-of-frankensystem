"""
Parser for the BOFS expression DSL.

Surface syntax is a strict subset of Python expression syntax. Parsing reuses
Python's ``ast`` module, then walks the resulting tree under a node whitelist
and emits a normalized JSON AST.

The output is plain ``dict`` / ``list`` / scalar — JSON-serializable as-is — so
the same AST can be evaluated server-side (Python) or shipped to the browser
and evaluated client-side (JavaScript).

AST node shapes::

    {"const": <scalar>}                       # int, float, str, bool, None
    {"var": "<name>"}                          # field reference
    {"op": "<op>", "args": [<node>, ...]}      # operations and list literals
    {"call": "<func>", "args": [<node>, ...]}  # whitelisted function call

Supported ``op`` values: ``+ - * / // %``, ``< <= > >= == !=``, ``and``,
``or``, ``not``, ``in``, ``not_in``, ``neg``, ``pos``, ``list``, ``if``.
"""

import ast


class ExpressionError(Exception):
    """Raised when an expression cannot be parsed under the BOFS DSL rules."""


# Function names callable from an expression. Implementations are provided by
# the evaluator's environment, not by this module — the parser only checks
# that the name appears in this whitelist.
ALLOWED_FUNCTIONS = frozenset({
    "len", "min", "max", "sum", "abs", "round",
    "mean", "median", "stdev", "std", "var", "variance",
    "int", "float", "str", "bool",
})


_CMP_OPS = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.In: "in",
    ast.NotIn: "not_in",
}

_BIN_OPS = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
}

_UNARY_OPS = {
    ast.UAdd: "pos",
    ast.USub: "neg",
    ast.Not: "not",
}


def parse(src):
    """
    Parse an expression string into a normalized JSON AST.

    Raises :class:`ExpressionError` on any syntax error or disallowed construct.
    """
    if not isinstance(src, str):
        raise ExpressionError(
            f"expected string expression, got {type(src).__name__}"
        )
    text = src.strip()
    if not text:
        raise ExpressionError("expression is empty")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"syntax error: {e.msg}") from e

    return _convert(tree.body)


def referenced_fields(node):
    """
    Return the set of variable names (``var`` nodes) referenced anywhere in
    a parsed AST. Function-call names are not included.
    """
    names = set()
    _walk_vars(node, names)
    return names


def _walk_vars(node, names):
    if isinstance(node, dict):
        if "var" in node:
            names.add(node["var"])
        else:
            for value in node.values():
                _walk_vars(value, names)
    elif isinstance(node, list):
        for value in node:
            _walk_vars(value, names)


def _convert(node):
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None or isinstance(value, (bool, int, float, str)):
            return {"const": value}
        raise ExpressionError(
            f"unsupported literal type: {type(value).__name__}"
        )

    if isinstance(node, ast.Name):
        return {"var": node.id}

    if isinstance(node, ast.BoolOp):
        op_name = "and" if isinstance(node.op, ast.And) else "or"
        return {"op": op_name, "args": [_convert(v) for v in node.values]}

    if isinstance(node, ast.BinOp):
        op_cls = type(node.op)
        if op_cls not in _BIN_OPS:
            raise ExpressionError(
                f"unsupported binary operator: {op_cls.__name__}"
            )
        return {
            "op": _BIN_OPS[op_cls],
            "args": [_convert(node.left), _convert(node.right)],
        }

    if isinstance(node, ast.UnaryOp):
        op_cls = type(node.op)
        if op_cls not in _UNARY_OPS:
            raise ExpressionError(
                f"unsupported unary operator: {op_cls.__name__}"
            )
        return {"op": _UNARY_OPS[op_cls], "args": [_convert(node.operand)]}

    if isinstance(node, ast.Compare):
        if len(node.ops) == 1:
            op_cls = type(node.ops[0])
            if op_cls not in _CMP_OPS:
                raise ExpressionError(
                    f"unsupported comparison operator: {op_cls.__name__}"
                )
            return {
                "op": _CMP_OPS[op_cls],
                "args": [_convert(node.left), _convert(node.comparators[0])],
            }
        # Chained comparisons (a < b < c) are flattened to AND of pairs.
        operands = [node.left, *node.comparators]
        clauses = []
        for i, op in enumerate(node.ops):
            op_cls = type(op)
            if op_cls not in _CMP_OPS:
                raise ExpressionError(
                    f"unsupported comparison operator: {op_cls.__name__}"
                )
            clauses.append({
                "op": _CMP_OPS[op_cls],
                "args": [_convert(operands[i]), _convert(operands[i + 1])],
            })
        return {"op": "and", "args": clauses}

    if isinstance(node, ast.Call):
        if node.keywords:
            raise ExpressionError("keyword arguments are not supported")
        if not isinstance(node.func, ast.Name):
            raise ExpressionError(
                "only direct function calls are supported (no attribute access)"
            )
        fname = node.func.id
        if fname not in ALLOWED_FUNCTIONS:
            raise ExpressionError(
                f"function {fname!r} is not allowed; "
                f"permitted functions: {sorted(ALLOWED_FUNCTIONS)}"
            )
        return {"call": fname, "args": [_convert(a) for a in node.args]}

    if isinstance(node, (ast.List, ast.Tuple)):
        return {"op": "list", "args": [_convert(e) for e in node.elts]}

    if isinstance(node, ast.IfExp):
        return {
            "op": "if",
            "args": [
                _convert(node.test),
                _convert(node.body),
                _convert(node.orelse),
            ],
        }

    raise ExpressionError(f"unsupported syntax: {type(node).__name__}")
