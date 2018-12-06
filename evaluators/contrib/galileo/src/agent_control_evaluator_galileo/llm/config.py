"""Configuration model for direct Galileo LLM-as-judge scorer evaluation."""

from __future__ import annotations

import os
from typing import Literal

from agent_control_evaluators import EvaluatorConfig
from agent_control_models import JSONValue
from pydantic import BaseModel, ConfigDict, Field, model_validator

LlmOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne", "contains", "any"]
LlmPayloadField = Literal["input", "output"]

_NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
LLM_EVALUATOR_FLAG_ENV = "GALILEO_FEATURE_FLAG_LLM_EVALUATOR"


def llm_evaluator_enabled() -> bool:
    """Return whether the LLM scorer invoke runtime is enabled.

    The LLM evaluator requires Orbit support for ``execution_context`` to fetch
    LLM credentials. Set ``GALILEO_FEATURE_FLAG_LLM_EVALUATOR=enabled`` once
    the Orbit-side support is confirmed ready.
    """
    return os.getenv(LLM_EVALUATOR_FLAG_ENV) == "enabled"


class ScorerInvokeConfig(BaseModel):
    """Orbit-supported overrides for a synchronous scorer invocation.

    Orbit owns the Galileo scorer-invoke wire contract. Keeping this model
    strict makes an unsupported option fail locally instead of producing a
    less actionable HTTP 422 response from Runners.

    Attributes:
        request_timeout_seconds: Optional upper bound for scorer execution in
            Orbit. The Agent Control HTTP and evaluator deadlines must remain
            longer than this value.
    """

    model_config = ConfigDict(extra="forbid")

    request_timeout_seconds: float | None = Field(default=None, gt=0)


def coerce_number(value: JSONValue) -> float | None:
    """Return a numeric value for JSON scalars that can be compared numerically."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class LlmEvaluatorConfig(EvaluatorConfig):
    """Configuration for direct LLM-as-judge scorer evaluation.

    Attributes:
