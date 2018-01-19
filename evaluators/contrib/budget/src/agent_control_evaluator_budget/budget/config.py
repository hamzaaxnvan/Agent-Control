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
    and time window. Multiple rules can apply to the same step -- the
    evaluator checks all of them and triggers on the first breach.

    Attributes:
        scope: Static scope dimensions that must match for this rule
            to apply. Empty dict = global rule.
            Examples:
                {"agent": "summarizer"} -- per-agent limit
                {"agent": "summarizer", "channel": "slack"} -- agent+channel limit
        group_by: If set, the limit is applied independently for each
            unique value of this dimension. e.g. group_by="user_id" means
            each user gets their own budget. None = shared/global limit.
        window_seconds: Time window for accumulation in seconds.
            None = cumulative (no reset). See WINDOW_* constants.
        limit: Maximum usage in the window. Interpreted by limit_unit.
        limit_unit: Unit for limit. usd_cents checks spend; tokens checks
            input + output tokens.
    """

    scope: dict[str, str] = Field(default_factory=dict)
    group_by: str | None = None
    window_seconds: int | None = None
    limit: int
    limit_unit: Literal["usd_cents", "tokens"] = "usd_cents"

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("limit must be a positive integer")
