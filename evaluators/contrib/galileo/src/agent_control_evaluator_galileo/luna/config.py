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

