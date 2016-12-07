"""Configuration for Galileo Decision Models scoring."""

from __future__ import annotations

import os
from typing import Literal

from agent_control_evaluators import EvaluatorConfig
from agent_control_models import JSONValue
from pydantic import Field, model_validator

DecisionModelsOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne", "contains", "any"]
DecisionModelsPayloadField = Literal["input", "output"]
_NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
SCORER_INVOKE_RUNTIME_FLAG_ENV = "GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME"
DECISION_MODELS_EVALUATOR_FLAG_ENV = "GALILEO_FEATURE_FLAG_DECISION_MODELS_EVALUATOR"


def scorer_invoke_runtime_enabled() -> bool:
    """Return whether structured runtime data is enabled for Decision Models requests."""
    return os.getenv(SCORER_INVOKE_RUNTIME_FLAG_ENV) == "enabled"


def decision_models_evaluator_enabled() -> bool:
    """Return whether the Decision Models evaluator is enabled for Agent Control."""
    return os.getenv(DECISION_MODELS_EVALUATOR_FLAG_ENV) == "enabled"
