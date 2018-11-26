"""DefenseClaw rule-pack evaluator."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_control_evaluators import Evaluator, EvaluatorMetadata, register_evaluator
from agent_control_models import EvaluatorResult

from ..common import no_op_result
from .config import DefenseClawRulePackConfig


def _resolve_package_version() -> str:
    try:
        return version("agent-control-evaluator-defenseclaw")
    except PackageNotFoundError:
        return "0.0.0.dev"


@register_evaluator
class DefenseClawRulePackEvaluator(Evaluator[DefenseClawRulePackConfig]):
    """Evaluate selected data with a typed DefenseClaw rule pack."""

    metadata = EvaluatorMetadata(
