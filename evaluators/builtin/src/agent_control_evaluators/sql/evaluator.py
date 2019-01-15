"""Comprehensive SQL validation evaluator.

Supports multi-statement, operation, table, column, and limit checking.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, cast

import sqlglot
from agent_control_models import EvaluatorResult
from sqlglot import exp

from agent_control_evaluators._base import Evaluator, EvaluatorMetadata
from agent_control_evaluators._registry import register_evaluator
from agent_control_evaluators.sql.config import SQLEvaluatorConfig

logger = logging.getLogger(__name__)


@dataclass
class QueryAnalysis:
    """Pre-computed analysis of a SQL query structure.

    Collected in a single tree walk for performance optimization.
    """
    # Operations
    operations: set[str] = field(default_factory=set)

    # Tables
    tables: list[tuple[str | None, str]] = field(default_factory=list)

    # Columns by context
    all_columns: list[str] = field(default_factory=list)
    top_level_where_columns: list[str] = field(default_factory=list)
    all_where_columns: list[str] = field(default_factory=list)
    top_level_select_columns: list[str] = field(default_factory=list)
    all_select_columns: list[str] = field(default_factory=list)

    # SELECT nodes (for LIMIT checks)
    select_nodes: list[exp.Select] = field(default_factory=list)

    # Query complexity metrics
    join_count: int = 0
    union_count: int = 0
    max_subquery_depth: int = 0

    # CTEs defined in the query (for table access checks)
    defined_ctes: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RequiredColumnValueRule:
    """Preprocessed required column/value mapping rule."""

    raw_column: str
    table: str | None
    column: str
    context_key: str


@register_evaluator
class SQLEvaluator(Evaluator[SQLEvaluatorConfig]):
    """Comprehensive SQL validation evaluator.

    Validates SQL queries in this order:
    1. Multi-Statement: Control whether multiple SQL statements are allowed
    2. Operations: Block/allow specific SQL operations (DROP, DELETE, etc.)
    3. Table/Schema Access: Restrict which tables/schemas can be accessed
    4. Column Presence: Require specific columns in queries (e.g., tenant_id)
    5. Limits: Require LIMIT clause and enforce max LIMIT value on SELECT queries

    Examples:
        # Block multi-statement queries
        {"allow_multi_statements": False}

        # Block dangerous operations
        {"blocked_operations": ["DROP", "DELETE", "TRUNCATE"]}

        # Read-only mode
        {"allowed_operations": ["SELECT"]}

        # Restrict table access
        {"allowed_tables": ["users", "orders"]}

        # Multi-tenant security
        {"required_columns": ["tenant_id"], "column_context": "where"}

        # Prevent large result sets
        {"require_limit": True, "max_limit": 1000}

        # Combined validation
        {
            "allow_multi_statements": False,
            "allowed_operations": ["SELECT"],
            "allowed_tables": ["users", "orders"],
            "required_columns": ["tenant_id"],
            "column_context": "where",
            "require_limit": True,
            "max_limit": 1000
        }
    """

    metadata = EvaluatorMetadata(
        name="sql",
        version="1.0.0",
        description=(
            "Comprehensive SQL validation: multi-statement, operations, "
            "table access, column presence, and limits"
        ),
        timeout_ms=10000,
    )
    config_model = SQLEvaluatorConfig

    # SQL operation type mappings
    DDL_OPERATIONS = {
        "CREATE",
        "ALTER",
        "DROP",
        "RENAME",
        "TRUNCATE",
        "COMMENT",
    }
    DML_OPERATIONS = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "CALL",
    }
    DCL_OPERATIONS = {
        "GRANT",
        "REVOKE",
    }
    TCL_OPERATIONS = {
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "SET TRANSACTION",
    }

    def __init__(self, config: SQLEvaluatorConfig) -> None:
        super().__init__(config)

        # Pre-process operation controls
        self._blocked_ops: set[str] | None = None
        self._allowed_ops: set[str] | None = None

        if config.blocked_operations:
            self._blocked_ops = {op.upper() for op in config.blocked_operations}
        elif config.allowed_operations:
            self._allowed_ops = {op.upper() for op in config.allowed_operations}

        # Add DDL/DCL to blocked if configured
        if config.block_ddl:
            self._blocked_ops = (self._blocked_ops or set()) | self.DDL_OPERATIONS
        if config.block_dcl:
            self._blocked_ops = (self._blocked_ops or set()) | self.DCL_OPERATIONS

        # Pre-process table/schema sets
        self._allowed_tables = self._build_set(
            config.allowed_tables, config.case_sensitive
        )
        self._blocked_tables = self._build_set(
            config.blocked_tables, config.case_sensitive
        )
        self._allowed_schemas = self._build_set(
            config.allowed_schemas, config.case_sensitive
        )
        self._blocked_schemas = self._build_set(
            config.blocked_schemas, config.case_sensitive
        )

        # Pre-process column sets
        self._required_columns = self._build_set(
            config.required_columns, config.case_sensitive
        )
        self._required_column_values = self._build_required_column_value_rules(
            config.required_column_values
        )

    def _build_set(self, items: list[str] | None, case_sensitive: bool) -> set[str] | None:
        """Build a set with proper casing."""
        if items is None:
            return None
        return {item if case_sensitive else item.lower() for item in items}

    def _normalize_name(self, name: str) -> str:
        """Normalize table/schema/column name for comparison."""
        return name if self.config.case_sensitive else name.lower()

    def _build_required_column_value_rules(
        self, rules: dict[str, str] | None
    ) -> list[RequiredColumnValueRule]:
        """Preprocess required column/value rules for fast matching."""
        if not rules:
            return []

        processed: list[RequiredColumnValueRule] = []
        for raw_column, context_key in rules.items():
            table_name: str | None = None
            column_name = raw_column

            if "." in raw_column:
                table_part, column_part = raw_column.split(".", 1)
                table_name = self._normalize_name(table_part.strip())
                column_name = column_part

            processed.append(
                RequiredColumnValueRule(
                    raw_column=raw_column,
                    table=table_name,
                    column=self._normalize_name(column_name.strip()),
                    context_key=context_key,
                )
            )

        return processed

    def _analyze_query_structure(self, stmt: exp.Expression) -> QueryAnalysis:
        """Analyze query structure in a single tree walk (performance optimization).

        Collects all necessary information for validation in one pass through the AST,
        avoiding multiple expensive tree traversals.

        Args:
            stmt: Parsed SQL statement (single statement)

        Returns:
            QueryAnalysis object with pre-computed metrics
        """
        analysis = QueryAnalysis()

        # Track top-level statement for context-aware column extraction
        top_level_select = stmt if isinstance(stmt, exp.Select) else None
        top_level_where = top_level_select.find(exp.Where) if top_level_select else None

        # Single tree walk to collect all metrics
        for raw_node in stmt.walk():
            node = cast(exp.Expression, raw_node)
            # Collect operations
            op_name = self._get_operation_name(node)
            if op_name:
                analysis.operations.add(op_name)

            # Collect SELECT nodes (for LIMIT checks)
            if isinstance(node, exp.Select):
                analysis.select_nodes.append(node)

            # Collect tables
            if isinstance(node, exp.Table):
                schema = node.db if node.db else None
                table_name = node.name if node.name else str(node)
                if table_name:
                    analysis.tables.append((schema, table_name))

            # Collect CTEs
            if isinstance(node, exp.CTE) and node.alias:
                analysis.defined_ctes.add(self._normalize_name(node.alias))

            # Count JOINs
            if isinstance(node, exp.Join):
                analysis.join_count += 1

            # Count set operations (UNION, INTERSECT, EXCEPT)
            if isinstance(node, (exp.Union, exp.Intersect, exp.Except)):
                analysis.union_count += 1

            # Collect columns
            if isinstance(node, exp.Column) and node.name:
                # All columns
                analysis.all_columns.append(node.name)

                # Top-level WHERE columns (excluding subqueries)
                if top_level_where and self._is_in_node_but_not_in_subqueries(
                    node, top_level_where
                ):
                    analysis.top_level_where_columns.append(node.name)

                # All WHERE columns (including subqueries)
                if self._is_in_where_clause(node):
                    analysis.all_where_columns.append(node.name)

                # Top-level SELECT columns
                if top_level_select and self._is_in_top_level_select(
                    node, top_level_select
                ):
                    analysis.top_level_select_columns.append(node.name)

                # All SELECT columns (including subqueries)
                if self._is_in_select_clause(node):
                    analysis.all_select_columns.append(node.name)

        # Calculate subquery depth
        analysis.max_subquery_depth = self._calculate_subquery_depth(stmt)

        return analysis

    def _is_in_node_but_not_in_subqueries(
        self, node: exp.Expression, target_node: exp.Expression
    ) -> bool:
        """Check if node is in target node but not in any nested SELECT subqueries."""
        # Walk up from node to see if we hit target_node before hitting a nested SELECT
        current = node.parent
        while current:
            if current is target_node:
                return True
            # If we hit a SELECT node before the target, node is in a subquery
            if isinstance(current, exp.Select) and current is not target_node:
                return False
            current = cast(exp.Expression | None, current.parent)
        return False

    def _is_in_where_clause(self, column: exp.Column) -> bool:
        """Check if column is in any WHERE clause (including subqueries)."""
        current = column.parent
        while current:
            if isinstance(current, exp.Where):
                return True
            current = cast(exp.Expression | None, current.parent)
        return False

    def _is_in_top_level_select(
        self, column: exp.Column, top_level_select: exp.Select
    ) -> bool:
        """Check if column is in top-level SELECT expressions (not subqueries)."""
        # Walk up from column to see if we're in the top-level SELECT
        current: exp.Expression | None = column
        while current:
            # If we hit the top-level SELECT, check if we're in its expressions
            if current is top_level_select:
                # Column is somewhere in this SELECT, but not in expressions list
                return False
            # If we're one of the top-level SELECT's expressions, we're top-level
            if current.parent is top_level_select and current in top_level_select.expressions:
                return True
            # If we hit another SELECT before the top-level, we're in a subquery
            if isinstance(current, exp.Select) and current is not top_level_select:
                return False
            current = cast(exp.Expression | None, current.parent)
        return False

    def _is_in_select_clause(self, column: exp.Column) -> bool:
        """Check if column is in any SELECT clause (including subqueries)."""
        current = cast(exp.Expression | None, column.parent)
        while current:
            # Check if this column is in a SELECT's expressions
            if isinstance(current, exp.Select):
                for select_expr in current.expressions:
                    if self._is_descendant_of(column, select_expr):
                        return True
                return False
            current = cast(exp.Expression | None, current.parent)
        return False

    def _is_descendant_of(
        self, node: exp.Expression, potential_ancestor: exp.Expression
    ) -> bool:
        """Check if node is a descendant of potential_ancestor."""
        current: exp.Expression | None = node
        while current:
            if current is potential_ancestor:
                return True
            current = cast(exp.Expression | None, current.parent)
        return False

    def _is_top_level_select(self, select_node: exp.Select) -> bool:
        """Check if a SELECT node is top-level (not nested in another SELECT).

        A SELECT is considered top-level if it's not nested inside another SELECT.
        This properly handles cases like:
        - Simple SELECT: top-level
        - SELECT in subquery: not top-level
        - SELECT inside CTE definition: not top-level (has outer SELECT as ancestor)
        - Main SELECT with CTEs: top-level (the outer SELECT, not the CTE body)
        - SELECT in CREATE VIEW: not top-level
        - SELECT in INSERT SELECT: not top-level

        Args:
            select_node: SELECT node to check

        Returns:
            True if top-level, False if nested in another SELECT
        """
        # Walk up parent chain looking for another SELECT
        current = select_node.parent
        while current:
            # If we find another SELECT before reaching root, we're nested
            if isinstance(current, exp.Select):
                return False
            current = current.parent
        # Reached root without finding parent SELECT - we're top-level
        return True

    def _check_multi_statements(
        self, parsed: list, query: str
    ) -> EvaluatorResult | None:
        """Check multi-statement controls.

        Args:
            parsed: List of parsed SQL statements
            query: Original SQL query string

        Returns:
            EvaluatorResult if multi-statement rules are violated, None otherwise
        """
        stmt_count = len([stmt for stmt in parsed if stmt is not None])

        # Check if multi-statements are disallowed
        if not self.config.allow_multi_statements and stmt_count > 1:
            return EvaluatorResult(
                matched=True,
                confidence=1.0,
                message=f"Multiple SQL statements not allowed (found {stmt_count} statements)",
                metadata={"statement_count": stmt_count, "query": query[:100]},
            )

        # Check max_statements limit
        if self.config.max_statements and stmt_count > self.config.max_statements:
            return EvaluatorResult(
                matched=True,
                confidence=1.0,
                message=(
                    f"Too many SQL statements: {stmt_count} "
                    f"(max: {self.config.max_statements})"
                ),
                metadata={
                    "statement_count": stmt_count,
                    "max_statements": self.config.max_statements,
                    "query": query[:100],
                },
            )

        return None

    def _check_limits(
        self, analyses: list[QueryAnalysis], query: str
    ) -> EvaluatorResult | None:
        """Check LIMIT clause requirements for all SELECT queries.

        Recursively checks all SELECT statements including subqueries to ensure
        resource limits cannot be bypassed.

        Args:
            analyses: Pre-computed query analyses
            query: Original SQL query string

        Returns:
            EvaluatorResult if LIMIT rules are violated, None otherwise
        """
        for analysis in analyses:
            # Use pre-computed SELECT nodes
            for select_node in analysis.select_nodes:
                # Use args.get() to get direct LIMIT child, not find() which searches descendants
                # This prevents a subquery's LIMIT from being attributed to the outer query
                limit_node = select_node.args.get("limit")

                # Check if LIMIT is required but missing
                if self.config.require_limit and not limit_node:
                    # Determine if this is a subquery or top-level using AST parent relationships
                    is_top_level = self._is_top_level_select(select_node)
                    violation_type = (
                        "missing_limit"
                        if is_top_level
                        else "missing_limit_in_subquery"
                    )
                    message = (
                        "SELECT query must have a LIMIT clause"
                        if is_top_level
                        else "All SELECT queries (including subqueries) must have a LIMIT clause"
                    )

                    return EvaluatorResult(
                        matched=True,
                        confidence=1.0,
                        message=message,
                        metadata={
                            "query": query[:100],
                            "violation": violation_type,
                        },
                    )

                # Check max_limit and max_result_window if LIMIT exists
                if limit_node:
                    limit_value = self._extract_limit_value(limit_node)

                    # Extract OFFSET value if present (use args.get() for direct child only)
                    offset_node = select_node.args.get("offset")
                    offset_value = 0
                    if offset_node:
                        offset_value = self._extract_offset_value(offset_node) or 0

                    # Check LIMIT value (skip if indeterminate)
                    if limit_value is not None:
                        # Check max_limit
                        if (
                            self.config.max_limit
                            and limit_value > self.config.max_limit
                        ):
                            return EvaluatorResult(
                                matched=True,
                                confidence=1.0,
                                message=(
                                    f"LIMIT value {limit_value} exceeds maximum "
                                    f"allowed {self.config.max_limit}"
                                ),
                                metadata={
                                    "limit_value": limit_value,
                                    "max_limit": self.config.max_limit,
                                    "query": query[:100],
                                },
                            )

                        # Check max_result_window (LIMIT + OFFSET)
                        if (
                            self.config.max_result_window
                            and offset_value is not None
                        ):
                            result_window = limit_value + offset_value
                            if result_window > self.config.max_result_window:
