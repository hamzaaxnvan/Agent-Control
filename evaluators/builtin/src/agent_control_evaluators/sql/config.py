"""Configuration for SQL validation evaluator."""

import warnings
from typing import Literal

from pydantic import Field, model_validator

from agent_control_evaluators._base import EvaluatorConfig


class SQLEvaluatorConfig(EvaluatorConfig):
    """Configuration for comprehensive SQL control evaluator.

    Validates SQL query strings using AST-based analysis via sqlglot.
    Controls are evaluated in order:
    syntax → multi-statement → operations → tables/schemas → columns → limits.
    """

    # Multi-Statement
    allow_multi_statements: bool = Field(
        default=True,
        description=(
            "Whether to allow multiple SQL statements in a single query. "
            "Set to False to prevent queries like 'SELECT x; DROP TABLE y' "
            "(SQL injection prevention)."
        ),
    )
    max_statements: int | None = Field(
        default=None,
        description=(
            "Maximum number of statements allowed (e.g., 2 allows up to 2 statements). "
            "Only applicable when allow_multi_statements=True."
        ),
    )

    # Operations
    blocked_operations: list[str] | None = Field(
        default=None,
        description=(
            "SQL operations to block (e.g., ['DROP', 'DELETE', 'TRUNCATE']). "
            "Cannot be used with allowed_operations."
        ),
    )
    allowed_operations: list[str] | None = Field(
        default=None,
        description=(
            "SQL operations to allow (e.g., ['SELECT'] for read-only). "
            "Cannot be used with blocked_operations."
        ),
    )
    block_ddl: bool = Field(
        default=False,
        description="Block all DDL operations (CREATE, ALTER, DROP, TRUNCATE, RENAME, COMMENT).",
    )
    block_dcl: bool = Field(
        default=False,
        description="Block all DCL operations (GRANT, REVOKE).",
    )

    # Table/Schema Access
    allowed_tables: list[str] | None = Field(
        default=None,
        description="Table names allowed (allowlist mode). Cannot be used with blocked_tables.",
    )
    blocked_tables: list[str] | None = Field(
        default=None,
        description="Table names to block (blocklist mode). Cannot be used with allowed_tables.",
    )
    allowed_schemas: list[str] | None = Field(
        default=None,
        description="Schema names allowed (allowlist mode). Cannot be used with blocked_schemas.",
    )
    blocked_schemas: list[str] | None = Field(
        default=None,
        description="Schema names to block (blocklist mode). Cannot be used with allowed_schemas.",
    )

    # Column Presence
    required_columns: list[str] | None = Field(
        default=None,
        description=(
            "Columns that must be present in the query "
            "(e.g., ['tenant_id'] for multi-tenant security)."
        ),
    )
    column_presence_logic: Literal["any", "all"] = Field(
        default="any",
        description="Matching logic for required_columns: 'any' or 'all'.",
    )
    column_context: Literal["select", "where"] | None = Field(
        default=None,
        description="Where required columns must appear: 'select', 'where', or None (anywhere).",
    )
    column_context_scope: Literal["top_level", "all"] = Field(
        default="all",
        description=(
            "Scope for column_context checking. "
            "'top_level': Only check top-level clause. "
            "'all': Check all clauses including subqueries."
        ),
    )
    required_column_values: dict[str, str] | None = Field(
        default=None,
        description=(
            "Map of column references to context keys for value-based tenant filtering. "
            "Each required column must appear in a top-level WHERE equality predicate "
            "with a literal value that matches the corresponding context value. "
            "Column references may be unqualified ('user_id') or table-qualified "
            "('users.user_id')."
        ),
    )

    # Limits
    require_limit: bool = Field(
        default=False,
        description="Require SELECT queries to have a LIMIT clause.",
    )
    max_limit: int | None = Field(
        default=None,
        description="Maximum allowed LIMIT value.",
    )
    max_result_window: int | None = Field(
        default=None,
        description="Maximum value of (LIMIT + OFFSET) for pagination control.",
    )

    # Options
    case_sensitive: bool = Field(
        default=False,
        description="Whether table/column/schema name matching is case sensitive.",
    )
    dialect: Literal["postgres", "mysql", "tsql", "oracle", "sqlite"] = Field(
        default="postgres",
        description="SQL dialect to use for parsing.",
    )

    # Query Complexity Limits
    max_subquery_depth: int | None = Field(
        default=None,
        description="Maximum nesting depth for subqueries.",
    )
    max_joins: int | None = Field(
        default=None,
        description="Maximum number of JOIN operations in a single query.",
    )
    max_union_count: int | None = Field(
        default=None,
        description="Maximum number of UNION/INTERSECT/EXCEPT operations.",
