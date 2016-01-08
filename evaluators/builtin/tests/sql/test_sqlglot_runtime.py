"""SQLGlot runtime integration tests."""

from sqlglot import exp

from agent_control_evaluators.sql import SQLEvaluator, SQLEvaluatorConfig


def test_sqlglot_public_imports_support_sql_evaluator():
