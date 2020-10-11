"""Tests for evaluator base classes.

Architecture: Evaluators take config at __init__, evaluate() only takes data.
"""

from typing import Any

import pytest

from agent_control_evaluators import Evaluator, EvaluatorConfig, EvaluatorMetadata
from agent_control_models import EvaluatorResult, Step


class MockConfig(EvaluatorConfig):
    """Config model for mock evaluator."""

    should_match: bool = False
    timeout_ms: int = 5000


class MockEvaluator(Evaluator[MockConfig]):
    """A mock evaluator for testing."""

    metadata = EvaluatorMetadata(
        name="mock-evaluator",
        version="1.0.0",
        description="A mock evaluator for testing",
        requires_api_key=False,
        timeout_ms=5000,
    )
    config_model = MockConfig

    async def evaluate(self, data: Any) -> EvaluatorResult:
