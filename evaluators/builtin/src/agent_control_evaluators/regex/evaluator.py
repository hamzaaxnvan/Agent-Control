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
