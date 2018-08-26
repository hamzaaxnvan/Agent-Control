"""Configuration for regex evaluator."""

import re2
from pydantic import Field, field_validator

from agent_control_evaluators._base import EvaluatorConfig


class RegexEvaluatorConfig(EvaluatorConfig):
    """Configuration for regex evaluator."""

    pattern: str = Field(..., description="Regular expression pattern (RE2 syntax)")
    flags: list[str] | None = Field(default=None, description="Regex flags (e.g., ['IGNORECASE'])")

    @field_validator("pattern")
