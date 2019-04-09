"""Tests for SQL evaluator."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from agent_control_models import EvaluatorResult
from agent_control_evaluators.sql import SQLEvaluator, SQLEvaluatorConfig


class TestEvaluatorResultValidator:
    """Tests for EvaluatorResult model validator."""

    def test_error_with_matched_true_raises_validation_error(self):
        """Should raise ValidationError when error is set with matched=True."""
        with pytest.raises(ValidationError) as exc_info:
            EvaluatorResult(
                matched=True,
                confidence=0.5,
                error="Some error",
            )
        assert "matched must be False when error is set" in str(exc_info.value)

    def test_error_with_matched_false_is_valid(self):
        """Should allow error when matched=False."""
        result = EvaluatorResult(
            matched=False,
            confidence=0.0,
            error="Some error",
        )
        # Check error first (convention)
        assert result.error == "Some error"
        assert result.matched is False

    def test_no_error_with_matched_true_is_valid(self):
        """Should allow matched=True when no error is set."""
        result = EvaluatorResult(
            matched=True,
            confidence=1.0,
            message="Blocked",
        )
        # Check error first (convention)
        assert result.error is None
        assert result.matched is True


class TestEvaluatorErrorHandling:
    """Tests for evaluator error handling (unexpected exceptions)."""

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self):
        """Should return error field when evaluator encounters unexpected exception."""
        config = SQLEvaluatorConfig(blocked_operations=["DROP"])
        evaluator = SQLEvaluator(config)

        # Simulate an unexpected exception in the internal method
        with patch.object(
            evaluator, "_evaluate_sync", side_effect=RuntimeError("Unexpected failure")
        ):
            result = await evaluator.evaluate("SELECT * FROM users")

        # Check error first (convention: error field takes precedence)
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "Unexpected failure" in result.error
        # When error is set, matched is enforced to be False (fail open)
        assert result.matched is False
        assert result.confidence == 0.0
        assert "unexpected error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_memory_error_returns_error(self):
        """Should handle MemoryError gracefully."""
        config = SQLEvaluatorConfig(blocked_operations=["DROP"])
        evaluator = SQLEvaluator(config)

        with patch.object(
            evaluator, "_evaluate_sync", side_effect=MemoryError("Out of memory")
        ):
            result = await evaluator.evaluate("SELECT * FROM users")

        # Check error first
        assert result.error is not None
        assert "MemoryError" in result.error
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_propagates(self):
        """KeyboardInterrupt should propagate (not be caught)."""
        config = SQLEvaluatorConfig(blocked_operations=["DROP"])
        evaluator = SQLEvaluator(config)

        with patch.object(
            evaluator, "_evaluate_sync", side_effect=KeyboardInterrupt()
        ):
            with pytest.raises(KeyboardInterrupt):
                await evaluator.evaluate("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_normal_validation_still_works_after_error(self):
        """Evaluator should continue working after an error."""
        config = SQLEvaluatorConfig(blocked_operations=["DROP"])
        evaluator = SQLEvaluator(config)

        # First call fails
        with patch.object(
            evaluator, "_evaluate_sync", side_effect=RuntimeError("Temporary failure")
        ):
            error_result = await evaluator.evaluate("SELECT * FROM users")

        assert error_result.error is not None

        # Second call should work normally (no patch)
        normal_result = await evaluator.evaluate("SELECT * FROM users")
        assert normal_result.error is None
        assert normal_result.matched is False


class TestSQLMultiStatement:
    """Tests for SQL multi-statement validation."""

    @pytest.mark.asyncio
    async def test_allow_multi_statements_by_default(self):
        """Should allow multiple statements by default."""
        config = SQLEvaluatorConfig()
        evaluator = SQLEvaluator(config)

        result = await evaluator.evaluate(
            "SELECT * FROM users; SELECT * FROM orders"
        )
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_block_multi_statements_when_disabled(self):
        """Should block multiple statements when allow_multi_statements=False."""
        config = SQLEvaluatorConfig(allow_multi_statements=False)
        evaluator = SQLEvaluator(config)

        # Single statement should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

        # Multiple statements should be blocked
        result = await evaluator.evaluate(
            "SELECT * FROM users; DELETE FROM logs"
        )
        assert result.error is None
        assert result.matched is True
        assert "2 statements" in result.message or "Multiple" in result.message
        assert result.metadata["statement_count"] == 2

    @pytest.mark.asyncio
    async def test_max_statements_limit(self):
        """Should enforce max_statements limit."""
        config = SQLEvaluatorConfig(max_statements=2)
        evaluator = SQLEvaluator(config)

        # 2 statements should pass
        result = await evaluator.evaluate(
            "SELECT * FROM users; SELECT * FROM orders"
        )
        assert result.error is None
        assert result.matched is False

        # 3 statements should be blocked
        result = await evaluator.evaluate(
            "SELECT * FROM users; SELECT * FROM orders; SELECT 1"
        )
        assert result.error is None
        assert result.matched is True
        assert result.metadata["statement_count"] == 3
        assert result.metadata["max_statements"] == 2

    @pytest.mark.asyncio
    async def test_max_statements_with_allow_false(self):
        """Should validate that max_statements requires allow_multi_statements."""
        # This should raise a validation error during config creation
        with pytest.raises(ValueError, match="max_statements is only applicable"):
            SQLEvaluatorConfig(allow_multi_statements=False, max_statements=3)


class TestSQLOperations:
    """Tests for SQL operation validation."""

    @pytest.mark.asyncio
    async def test_block_drop_operation(self):
        """Should block DROP operations."""
        config = SQLEvaluatorConfig(blocked_operations=["DROP"])
        evaluator = SQLEvaluator(config)

        result = await evaluator.evaluate("DROP TABLE users")

        assert result.error is None
        assert result.matched is True
        assert "DROP" in result.message
        assert "DROP" in result.metadata["blocked"]

    @pytest.mark.asyncio
    async def test_block_multiple_dangerous_operations(self):
        """Should block multiple dangerous operations."""
        config = SQLEvaluatorConfig(
            blocked_operations=["DROP", "DELETE", "TRUNCATE"]
        )
        evaluator = SQLEvaluator(config)

        # Test DROP
        result = await evaluator.evaluate("DROP TABLE users")
        assert result.error is None
        assert result.matched is True

        # Test DELETE
        result = await evaluator.evaluate("DELETE FROM users WHERE id = 1")
        assert result.error is None
        assert result.matched is True

        # Test TRUNCATE
        result = await evaluator.evaluate("TRUNCATE TABLE users")
        assert result.error is None
        assert result.matched is True

    @pytest.mark.asyncio
    async def test_allow_safe_operations_when_blocking_dangerous(self):
        """Should allow safe operations when blocking dangerous ones."""
        config = SQLEvaluatorConfig(
            blocked_operations=["DROP", "DELETE", "TRUNCATE"]
        )
        evaluator = SQLEvaluator(config)

        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

        result = await evaluator.evaluate("INSERT INTO users (name) VALUES ('test')")
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_allowlist_mode_select_only(self):
        """Should allow only SELECT when in allowlist mode."""
        config = SQLEvaluatorConfig(allowed_operations=["SELECT"])
        evaluator = SQLEvaluator(config)

        # SELECT should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

        # Other operations should be blocked
        result = await evaluator.evaluate("INSERT INTO users (name) VALUES ('test')")
        assert result.error is None
        assert result.matched is True
        assert "INSERT" in result.metadata["blocked"]

        result = await evaluator.evaluate("UPDATE users SET name = 'new' WHERE id = 1")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("DELETE FROM users WHERE id = 1")
        assert result.error is None
        assert result.matched is True

    @pytest.mark.asyncio
    async def test_block_ddl_flag(self):
        """Should block all DDL operations when block_ddl=True."""
        config = SQLEvaluatorConfig(block_ddl=True)
        evaluator = SQLEvaluator(config)

        # DDL operations should be blocked
        result = await evaluator.evaluate("CREATE TABLE test (id INT)")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("ALTER TABLE users ADD COLUMN age INT")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("DROP TABLE users")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("TRUNCATE TABLE users")
        assert result.error is None
        assert result.matched is True

        # DML operations should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_block_dcl_flag(self):
        """Should block all DCL operations when block_dcl=True."""
        config = SQLEvaluatorConfig(block_dcl=True)
        evaluator = SQLEvaluator(config)

        # DCL operations should be blocked
        result = await evaluator.evaluate("GRANT SELECT ON users TO user1")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("REVOKE SELECT ON users FROM user1")
        assert result.error is None
        assert result.matched is True

        # Other operations should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_multiple_statements(self):
        """Should detect blocked operations in multiple statements."""
        config = SQLEvaluatorConfig(blocked_operations=["DROP"])
        evaluator = SQLEvaluator(config)

        result = await evaluator.evaluate(
            "SELECT * FROM users; DROP TABLE users; SELECT 1"
        )
        assert result.error is None
        assert result.matched is True
        assert "DROP" in result.metadata["blocked"]


class TestSQLTableAccess:
    """Tests for SQL table/schema access validation."""

    @pytest.mark.asyncio
    async def test_allow_specific_tables(self):
        """Should allow only specific tables."""
        config = SQLEvaluatorConfig(allowed_tables=["users", "orders"])
        evaluator = SQLEvaluator(config)

        # Allowed tables should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

        result = await evaluator.evaluate("SELECT * FROM orders")
        assert result.error is None
        assert result.matched is False

        # Other tables should be blocked
        result = await evaluator.evaluate("SELECT * FROM admin")
        assert result.error is None
        assert result.matched is True
        assert "admin" in result.message

    @pytest.mark.asyncio
    async def test_block_specific_tables(self):
        """Should block specific tables."""
        config = SQLEvaluatorConfig(blocked_tables=["admin", "secrets"])
        evaluator = SQLEvaluator(config)

        # Blocked tables should be blocked
        result = await evaluator.evaluate("SELECT * FROM admin")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("SELECT * FROM secrets")
        assert result.error is None
        assert result.matched is True

        # Other tables should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_block_system_schemas(self):
        """Should block system schemas."""
        config = SQLEvaluatorConfig(
            blocked_schemas=["pg_catalog", "information_schema"]
        )
        evaluator = SQLEvaluator(config)

        # System schemas should be blocked
        result = await evaluator.evaluate("SELECT * FROM pg_catalog.pg_tables")
        assert result.error is None
        assert result.matched is True
        assert "pg_catalog" in result.message

        result = await evaluator.evaluate(
            "SELECT * FROM information_schema.tables"
        )
        assert result.error is None
        assert result.matched is True

        # Regular queries should pass
        result = await evaluator.evaluate("SELECT * FROM users")
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_qualified_table_names(self):
        """Should handle qualified table names (schema.table)."""
        config = SQLEvaluatorConfig(
            allowed_schemas=["public"], blocked_tables=["admin"]
        )
        evaluator = SQLEvaluator(config)

        # Public schema should pass
        result = await evaluator.evaluate("SELECT * FROM public.users")
        assert result.error is None
        assert result.matched is False

        # Non-public schema should be blocked
        result = await evaluator.evaluate("SELECT * FROM private.users")
        assert result.error is None
        assert result.matched is True

        # Blocked table even in allowed schema should be blocked
        result = await evaluator.evaluate("SELECT * FROM public.admin")
        assert result.error is None
        assert result.matched is True

    @pytest.mark.asyncio
    async def test_multiple_tables_in_query(self):
        """Should check all tables in a query."""
        config = SQLEvaluatorConfig(allowed_tables=["users", "orders"])
        evaluator = SQLEvaluator(config)

        # All allowed tables
        result = await evaluator.evaluate(
            "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
        )
        assert result.error is None
        assert result.matched is False

        # One disallowed table
        result = await evaluator.evaluate(
            "SELECT * FROM users JOIN admin ON users.id = admin.user_id"
        )
        assert result.error is None
        assert result.matched is True
        assert "admin" in result.message

    @pytest.mark.asyncio
    async def test_case_sensitivity_tables(self):
        """Should respect case sensitivity setting for tables."""
        # Case insensitive (default)
        config = SQLEvaluatorConfig(
            blocked_tables=["admin"], case_sensitive=False
        )
        evaluator = SQLEvaluator(config)

        result = await evaluator.evaluate("SELECT * FROM Admin")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("SELECT * FROM ADMIN")
        assert result.error is None
        assert result.matched is True

        # Case sensitive
        config = SQLEvaluatorConfig(blocked_tables=["admin"], case_sensitive=True)
        evaluator = SQLEvaluator(config)

        result = await evaluator.evaluate("SELECT * FROM admin")
        assert result.error is None
        assert result.matched is True

        result = await evaluator.evaluate("SELECT * FROM Admin")
        assert result.error is None
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_cte_not_treated_as_table_violation(self):
        """Should not treat CTEs as unauthorized table access."""
        config = SQLEvaluatorConfig(allowed_tables=["users"], case_sensitive=False)
        evaluator = SQLEvaluator(config)

        # CTE 'temp_users' is defined locally, not in allowed_tables
        # This should pass because CTEs are not external tables
        query = """
        WITH temp_users AS (
            SELECT * FROM users WHERE id > 100
        )
        SELECT * FROM temp_users
        """
        result = await evaluator.evaluate(query)
        assert result.error is None
        assert result.matched is False

        # Multiple CTEs should also work
        query = """
        WITH
            active_users AS (SELECT * FROM users WHERE active = true),
            premium_users AS (SELECT * FROM active_users WHERE premium = true)
        SELECT * FROM premium_users
        """
        result = await evaluator.evaluate(query)
        assert result.error is None
        assert result.matched is False

        # But accessing unauthorized real tables should still be blocked
        query = """
        WITH temp_data AS (
            SELECT * FROM admin WHERE id > 100
        )
        SELECT * FROM temp_data
        """
        result = await evaluator.evaluate(query)
        assert result.error is None
        assert result.matched is True
        assert "admin" in result.message


class TestSQLColumnPresence:
    """Tests for SQL column presence validation."""

    @pytest.mark.asyncio
    async def test_require_column_in_where_clause(self):
        """Should require specific column in WHERE clause."""
        config = SQLEvaluatorConfig(
            required_columns=["tenant_id"], column_context="where"
        )
        evaluator = SQLEvaluator(config)

        # Query with tenant_id in WHERE - should pass
        result = await evaluator.evaluate(
            "SELECT * FROM users WHERE tenant_id = 123"
        )
        assert result.error is None
        assert result.matched is False

        # Query without tenant_id in WHERE - should be blocked
        result = await evaluator.evaluate("SELECT * FROM users WHERE id = 1")
        assert result.error is None
        assert result.matched is True
        assert "tenant_id" in result.message

        # Query with tenant_id in SELECT but not WHERE - should be blocked
        result = await evaluator.evaluate(
            "SELECT tenant_id FROM users WHERE id = 1"
        )
        assert result.error is None
        assert result.matched is True

    @pytest.mark.asyncio
    async def test_require_column_in_select_clause(self):
        """Should require specific column in SELECT clause."""
        config = SQLEvaluatorConfig(
            required_columns=["id", "created_at"],
            column_presence_logic="all",
            column_context="select"
        )
        evaluator = SQLEvaluator(config)

        # Query with both columns in SELECT - should pass
        result = await evaluator.evaluate(
            "SELECT id, name, created_at FROM users"
        )
        assert result.error is None
        assert result.matched is False

        # Query missing one column - should be blocked
        result = await evaluator.evaluate("SELECT id, name FROM users")
        assert result.error is None
        assert result.matched is True
        assert "created_at" in result.message
