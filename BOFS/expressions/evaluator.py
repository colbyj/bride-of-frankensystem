"""
Pure-Python evaluator for the BOFS expression AST.

Operates on the JSON AST shape produced by :mod:`BOFS.expressions.parser`.
The evaluator carries no globals, no imports, and no eval — every value comes
either from the AST itself (constants, function names) or from the ``env``
dict supplied by the caller (variable values, function implementations).
"""

from .parser import ALLOWED_FUNCTIONS, ExpressionError


def default_functions():
    """
    Return the default function implementations: standard reductions and
    BOFS's stats helpers from :mod:`BOFS.util`. Imported lazily so the
    expression engine has no hard dependency on the rest of BOFS.
    """
    from BOFS.util import mean, median, stdev, std, var, variance
    return {
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "abs": abs,
        "round": round,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "mean": mean,
        "median": median,
        "stdev": stdev,
        "std": std,
        "var": var,
        "variance": variance,
    }


def evaluate(node, env, functions=None):
    """
    Evaluate a parsed AST node.

    :param node: The AST produced by :func:`BOFS.expressions.parser.parse`.
    :param env: Mapping of variable names to values.
    :param functions: Mapping of function names to callables. When ``None``,
        :func:`default_functions` is used.
    :returns: The expression's value.
    """
    if functions is None:
        functions = default_functions()
    return _eval(node, env, functions)


def _eval(node, env, functions):
    if not isinstance(node, dict):
        raise ExpressionError(f"malformed AST node: {node!r}")

    if "const" in node:
        return node["const"]

    if "var" in node:
        name = node["var"]
        if name not in env:
            raise ExpressionError(f"undefined variable: {name!r}")
        return env[name]

    if "call" in node:
        fname = node["call"]
        if fname not in ALLOWED_FUNCTIONS:
            raise ExpressionError(f"function {fname!r} is not allowed")
        if fname not in functions:
            raise ExpressionError(f"function {fname!r} has no implementation")
        args = [_eval(a, env, functions) for a in node.get("args", [])]
        return functions[fname](*args)

    if "op" not in node:
        raise ExpressionError(f"malformed AST node: {node!r}")

    op = node["op"]
    args = node.get("args", [])

    # Short-circuit logical ops — do NOT pre-evaluate all args.
    if op == "and":
        result = True
        for a in args:
            result = _eval(a, env, functions)
            if not result:
                return result
        return result

    if op == "or":
        result = False
        for a in args:
            result = _eval(a, env, functions)
            if result:
                return result
        return result

    if op == "if":
        if len(args) != 3:
            raise ExpressionError("'if' expects exactly 3 arguments")
        test = _eval(args[0], env, functions)
        return _eval(args[1] if test else args[2], env, functions)

    # Eager ops: evaluate all args, then apply.
    values = [_eval(a, env, functions) for a in args]

    if op == "list":
        return values

    if op == "not":
        return not values[0]
    if op == "neg":
        return -values[0]
    if op == "pos":
        return +values[0]

    if len(values) != 2:
        raise ExpressionError(f"operator {op!r} expects 2 arguments, got {len(values)}")
    a, b = values

    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a / b
    if op == "//":
        return a // b
    if op == "%":
        return a % b

    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "==":
        return a == b
    if op == "!=":
        return a != b

    if op == "in":
        return a in b
    if op == "not_in":
        return a not in b

    raise ExpressionError(f"unknown operator: {op!r}")
