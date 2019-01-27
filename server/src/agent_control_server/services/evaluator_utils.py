"""Utilities for working with evaluator references.

Evaluator Type Name Formats:
    - Built-in: "regex", "list", "json", "sql"
    - External: "galileo.luna", "nvidia.nemo" (dot separator)
    - Agent-scoped: "my-agent:pii-detector" (colon separator)

The key distinction is:
    - Built-in and external evaluators are global (available to all agents)
    - Agent-scoped evaluators are custom implementations deployed with a specific agent
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from jsonschema_rs import validator_for


@dataclass
class ParsedEvaluatorRef:
    """Parsed evaluator reference with type information.

    Attributes:
        type: The evaluator category ("builtin", "external", or "agent")
        name: The full evaluator name (e.g., "regex", "galileo.luna", "my-agent:pii")
        namespace: For external evaluators, the provider name; for agent-scoped, the agent name
        local_name: The evaluator name without namespace prefix
    """

    type: Literal["builtin", "external", "agent"]
    name: str
    namespace: str | None
    local_name: str


def parse_evaluator_ref_full(evaluator_ref: str) -> ParsedEvaluatorRef:
    """Parse evaluator reference into structured form with type detection.

    Determines the evaluator type based on the name format:
    - Contains ":" → agent-scoped (split on first ":")
    - Contains "." → external (split on first ".")
    - Otherwise → built-in

    Args:
        evaluator_ref: Evaluator reference string

    Returns:
        ParsedEvaluatorRef with type, namespace, and local name

    Examples:
        >>> parse_evaluator_ref_full("regex")
        ParsedEvaluatorRef(type="builtin", name="regex", ...)

        >>> parse_evaluator_ref_full("galileo.luna")
        ParsedEvaluatorRef(type="external", namespace="galileo", ...)

        >>> parse_evaluator_ref_full("my-agent:pii-detector")
        ParsedEvaluatorRef(type="agent", namespace="my-agent", ...)
    """
    if ":" in evaluator_ref:
        # Agent-scoped: "my-agent:pii-detector"
        agent, local_name = evaluator_ref.split(":", 1)
        return ParsedEvaluatorRef(
            type="agent",
            name=evaluator_ref,
            namespace=agent,
            local_name=local_name,
        )
    elif "." in evaluator_ref:
        # External: "galileo.luna"
        provider, local_name = evaluator_ref.split(".", 1)
        return ParsedEvaluatorRef(
            type="external",
            name=evaluator_ref,
            namespace=provider,
            local_name=local_name,
        )
    else:
        # Built-in: "regex"
        return ParsedEvaluatorRef(
            type="builtin",
            name=evaluator_ref,
            namespace=None,
            local_name=evaluator_ref,
        )


def is_agent_scoped(evaluator_ref: str) -> bool:
    """Check if an evaluator reference is agent-scoped.

    Agent-scoped evaluators use the "agent:name" format and reference
    custom implementations deployed with a specific agent.

    Args:
        evaluator_ref: Evaluator reference string

