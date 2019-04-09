"""Configuration for the budget evaluator."""

from __future__ import annotations

from typing import Literal

from agent_control_evaluators._base import EvaluatorConfig
from pydantic import Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Window convenience constants (seconds)
# ---------------------------------------------------------------------------

WINDOW_HOURLY = 3600
WINDOW_DAILY = 86400
WINDOW_WEEKLY = 604800
WINDOW_MONTHLY = 2592000  # 30 days


class ModelPricing(EvaluatorConfig):
    """Per-model token pricing in cents per 1K tokens."""

    input_per_1k: float = 0.0
    output_per_1k: float = 0.0


class BudgetLimitRule(EvaluatorConfig):
    """A single budget limit rule.

    Each rule defines a ceiling for a combination of scope dimensions
