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
