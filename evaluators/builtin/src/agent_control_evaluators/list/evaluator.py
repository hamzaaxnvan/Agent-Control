"""List evaluator for value matching."""

import re
from typing import Any

import re2
from agent_control_models import EvaluatorResult

from agent_control_evaluators._base import Evaluator, EvaluatorMetadata
from agent_control_evaluators._registry import register_evaluator
from agent_control_evaluators.list.config import ListEvaluatorConfig


@register_evaluator
class ListEvaluator(Evaluator[ListEvaluatorConfig]):
    """List-based value matching evaluator.

    Checks if data matches values in a list. Supports:
    - any/all logic (match any value vs match all values)
    - match/no_match trigger (trigger on match or no match)
    - exact/contains/starts_with/ends_with mode (full match vs keyword vs prefix/suffix)
    - case sensitivity toggle

    Example configs:
        {"values": ["admin", "root"], "logic": "any"}  # Block admin/root
        {"values": ["approved"], "match_on": "no_match"}  # Require approval
    """

    metadata = EvaluatorMetadata(
        name="list",
        version="1.0.0",
        description="List-based value matching with flexible logic",
    )
    config_model = ListEvaluatorConfig

