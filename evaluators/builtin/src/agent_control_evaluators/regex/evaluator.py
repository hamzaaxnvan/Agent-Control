"""Regex evaluator for pattern matching."""

from typing import Any

import re2
from agent_control_models import EvaluatorResult

from agent_control_evaluators._base import Evaluator, EvaluatorMetadata
from agent_control_evaluators._registry import register_evaluator
from agent_control_evaluators.regex.config import RegexEvaluatorConfig


@register_evaluator
class RegexEvaluator(Evaluator[RegexEvaluatorConfig]):
    """Regular expression pattern matching evaluator.

    Matches data against a regex pattern using Google RE2 for safety
    (protects against ReDoS attacks).

    Supported flags:
        - IGNORECASE / I: Case-insensitive matching

    Example config:
        {"pattern": "\\\\d{3}-\\\\d{2}-\\\\d{4}"}  # SSN pattern
        {"pattern": "secret", "flags": ["IGNORECASE"]}  # Case-insensitive
    """

    metadata = EvaluatorMetadata(
        name="regex",
        version="1.0.0",
        description="Regular expression pattern matching (RE2)",
    )
    config_model = RegexEvaluatorConfig

    def __init__(self, config: RegexEvaluatorConfig) -> None:
        super().__init__(config)
