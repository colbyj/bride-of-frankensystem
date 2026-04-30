"""
BOFS expression engine.

A small Python-like DSL parsed once on the server into a normalized JSON AST.
The same AST is evaluable in Python (this package) and JavaScript
(``BOFS/static/js/bofs_expressions.js``), so a single expression string can
drive both server-side decisions (page-level skip, participant_calculations)
and live client-side question show/hide.

Public surface:

    from BOFS.expressions import parse, evaluate, referenced_fields, ExpressionError
"""

from .parser import parse, referenced_fields, ExpressionError, ALLOWED_FUNCTIONS
from .evaluator import evaluate, default_functions
from .fields import parse_with_field_ids
from .participant_env import parse_page_predicate, build_env as build_participant_env

__all__ = [
    "parse",
    "parse_with_field_ids",
    "parse_page_predicate",
    "build_participant_env",
    "evaluate",
    "referenced_fields",
    "ExpressionError",
    "ALLOWED_FUNCTIONS",
    "default_functions",
]
