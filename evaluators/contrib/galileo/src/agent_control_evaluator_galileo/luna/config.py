"""Configuration model for direct Galileo Luna scorer evaluation."""

from __future__ import annotations

import os
from typing import Literal

from agent_control_evaluators import EvaluatorConfig
from agent_control_models import JSONValue
from pydantic import BaseModel, ConfigDict, Field, model_validator

LunaOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne", "contains", "any"]
LunaPayloadField = Literal["input", "output"]

_NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
SCORER_INVOKE_RUNTIME_FLAG_ENV = "GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME"


def scorer_invoke_runtime_enabled() -> bool:
    """Return whether structured runtime data is enabled for Luna requests."""
    return os.getenv(SCORER_INVOKE_RUNTIME_FLAG_ENV) == "enabled"


class ScorerInvokeConfig(BaseModel):
    """Orbit-supported overrides for a synchronous scorer invocation.

    Orbit owns the Galileo scorer-invoke wire contract. Keeping this model
    strict makes an unsupported option fail locally instead of producing a
    less actionable HTTP 422 response from Runners.

    Attributes:
        threshold: Legacy threshold accepted by Orbit. Agent Control still
            applies its evaluator threshold locally.
        score_threshold: Legacy score threshold accepted by Orbit.
        request_timeout_seconds: Optional upper bound for scorer execution in
            Orbit. The Agent Control HTTP and evaluator deadlines must remain
            longer than this value.
    """

    model_config = ConfigDict(extra="forbid")

    threshold: float | None = None
    score_threshold: float | None = None
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


class LunaEvaluatorConfig(EvaluatorConfig):
    """Configuration for direct Luna scorer evaluation.

    Attributes:
        scorer_id: Required scorer identifier for Luna scorer invocation.
        scorer_version_id: Optional for legacy requests; required when the
            contextual evaluator sends a structured record.
        scorer_label: Optional display/metadata label.
        threshold: Local threshold used by the evaluator for comparison.
        operator: Local comparison operator. Numeric operators use threshold as a number.
        scorer_config: Optional Orbit-supported scorer invocation config sent
            as ``config``.
        payload_field: Explicit scorer input side for scalar selected data.
        timeout_ms: Request timeout in milliseconds.
    """

    scorer_id: str = Field(
        min_length=1,
