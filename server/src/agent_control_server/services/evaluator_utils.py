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
