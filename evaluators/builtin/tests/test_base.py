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
        """Simple mock evaluation."""
        return EvaluatorResult(
            matched=self.config.should_match,
            confidence=1.0,
            message="Mock evaluation",
            metadata={"data": str(data)},
        )


class TestEvaluatorMetadata:
    """Tests for EvaluatorMetadata dataclass."""

    def test_metadata_with_defaults(self):
        """Test metadata with default values."""
        metadata = EvaluatorMetadata(
            name="test-evaluator",
            version="1.0.0",
            description="Test evaluator",
        )

        assert metadata.name == "test-evaluator"
        assert metadata.version == "1.0.0"
        assert metadata.description == "Test evaluator"
        assert metadata.requires_api_key is False
        assert metadata.timeout_ms == 10000

    def test_metadata_with_all_fields(self):
        """Test metadata with all fields specified."""
        metadata = EvaluatorMetadata(
            name="full-evaluator",
            version="2.0.0",
            description="Full evaluator",
            requires_api_key=True,
            timeout_ms=15000,
