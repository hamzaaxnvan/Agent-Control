"""Agent Control Evaluators.

This package contains builtin evaluator implementations for agent-control.
Built-in evaluators (regex, list, json, sql) are registered automatically on import.

Available evaluators:
    Built-in (no namespace):
        - regex: Regular expression matching
        - list: List-based value matching
        - json: JSON validation
        - sql: SQL query validation

Naming convention:
    - Built-in: "regex", "list", "json", "sql"
    - External: "provider.name" (e.g., "galileo.luna")
    - Agent-scoped: "agent:name" (custom code deployed with agent)

External evaluators are installed via separate packages (e.g., agent-control-evaluator-galileo).
Custom evaluators are Evaluator classes deployed with the engine.
Their schemas are registered via initAgent for validation purposes.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-control-evaluators")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

# Core infrastructure - export from _base and _registry
from agent_control_evaluators._base import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorMetadata,
)
from agent_control_evaluators._discovery import (
    discover_evaluators,
    ensure_evaluators_discovered,
    list_evaluators,
    reset_evaluator_discovery,
