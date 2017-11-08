"""Unit tests for the evaluator system.

Tests evaluator registration, discovery, and base functionality without
requiring actual evaluator implementations or external services.

Evaluators take config at __init__, evaluate() only takes data.
Registry, base classes, and discovery are in agent_control_evaluators.
"""

import pytest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from agent_control.evaluators import (
    Evaluator,
    EvaluatorMetadata,
    discover_evaluators,
    list_evaluators,
    register_evaluator,
)
from agent_control_evaluators import clear_evaluators
from agent_control_engine import reset_evaluator_discovery
from agent_control_models.controls import EvaluatorResult


class MockConfig(BaseModel):
    """Config model for MockEvaluator."""
    threshold: float = 0.5


class MockEvaluator(Evaluator):
    """Mock evaluator for testing.

    Config is passed at __init__, not at evaluate().
    """

    metadata = EvaluatorMetadata(
        name="test-mock-evaluator",
        version="1.0.0",
        description="Mock evaluator for testing",
        requires_api_key=False,
        timeout_ms=10,
    )
    config_model = MockConfig

    def __init__(self, config: dict):
        super().__init__(config)
        self.threshold = config.get("threshold", 0.5)

    def evaluate(self, data) -> EvaluatorResult:
        """Mock evaluation (synchronous)."""
        matched = float(data) > self.threshold if isinstance(data, (int, float)) else False
        return EvaluatorResult(
            matched=matched,
            confidence=1.0,
            message=f"Mock evaluation: {matched}",
            metadata={"threshold": self.threshold},
        )


class TestEvaluatorMetadata:
    """Tests for EvaluatorMetadata dataclass."""

    def test_metadata_creation(self):
