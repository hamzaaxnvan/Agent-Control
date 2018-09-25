"""Targeted tests for SQLEvaluatorConfig validate_config branches."""

from __future__ import annotations

import warnings

import pytest
from agent_control_evaluators.sql.config import SQLEvaluatorConfig


class TestConflictingRestrictions:
    """Mutually-exclusive allow/block lists must be rejected at config time."""

    def test_blocked_and_allowed_operations_conflict(self):
        with pytest.raises(ValueError, match="blocked_operations and allowed_operations"):
            SQLEvaluatorConfig(
                blocked_operations=["DELETE"],
                allowed_operations=["SELECT"],
            )

    def test_blocked_and_allowed_tables_conflict(self):
        with pytest.raises(ValueError, match="allowed_tables and blocked_tables"):
            SQLEvaluatorConfig(
                allowed_tables=["users"],
                blocked_tables=["secrets"],
            )

    def test_blocked_and_allowed_schemas_conflict(self):
        with pytest.raises(ValueError, match="allowed_schemas and blocked_schemas"):
            SQLEvaluatorConfig(
                allowed_schemas=["public"],
                blocked_schemas=["internal"],
            )


class TestLimitBounds:
    """Numeric controls must be positive."""

    def test_max_limit_must_be_positive(self):
        with pytest.raises(ValueError, match="max_limit must be a positive integer"):
            SQLEvaluatorConfig(max_limit=0)

    def test_max_limit_negative_rejected(self):
        with pytest.raises(ValueError, match="max_limit must be a positive integer"):
            SQLEvaluatorConfig(max_limit=-5)

    def test_max_statements_must_be_positive(self):
        with pytest.raises(ValueError, match="max_statements must be a positive integer"):
            SQLEvaluatorConfig(
                allow_multi_statements=True,
                max_statements=0,
            )


class TestColumnControls:
    """Column-level validators cover required_column_values shape rules."""

    def test_column_context_without_required_columns_warns(self):
        with pytest.warns(UserWarning, match="column_context is set but required_columns"):
            SQLEvaluatorConfig(column_context="where")

    def test_required_column_values_rejects_empty_column_ref(self):
        with pytest.raises(ValueError, match="empty column reference"):
            SQLEvaluatorConfig(
                required_columns=["tenant_id"],
                required_column_values={"   ": "tenant_id"},
            )

