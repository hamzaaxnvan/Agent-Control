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
