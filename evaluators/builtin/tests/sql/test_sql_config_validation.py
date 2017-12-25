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

