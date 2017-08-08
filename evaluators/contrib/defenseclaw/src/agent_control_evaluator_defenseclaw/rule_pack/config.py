"""Typed configuration for the DefenseClaw rule-pack evaluator."""

from __future__ import annotations

from typing import Literal, Self

from agent_control_evaluators import EvaluatorConfig
from pydantic import BaseModel, Field, model_validator

from ..common import STRICT_PROVIDER_CONFIG, NonEmptyString, Severity


class RuleConfig(BaseModel):
    """One DefenseClaw rule."""

    model_config = STRICT_PROVIDER_CONFIG

    id: NonEmptyString
    pattern: NonEmptyString
    title: NonEmptyString
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    tags: list[NonEmptyString]


