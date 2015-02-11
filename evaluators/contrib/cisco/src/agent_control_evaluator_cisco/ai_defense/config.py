from __future__ import annotations

from typing import Any, Literal

from agent_control_evaluators import EvaluatorConfig
from pydantic import Field


class CiscoAIDefenseConfig(EvaluatorConfig):
    """Configuration for Cisco AI Defense evaluator (REST).

    Attributes:
        api_key_env: Env var name for API key
        region: Optional server region (us, ap, eu); ignored if api_url set
        api_url: Optional full endpoint override
        timeout_ms: Request timeout (milliseconds)
