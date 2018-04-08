"""Tests for evaluator system integration with the unified architecture.

These tests verify the evaluator system works correctly with the engine.
"""

from typing import Any

# Import to ensure built-in evaluators are registered
import agent_control_evaluators  # noqa: F401
import pytest
from agent_control_engine import get_evaluator_instance
from agent_control_evaluators import Evaluator, EvaluatorMetadata, register_evaluator
from agent_control_models import EvaluatorResult, EvaluatorSpec
from pydantic import BaseModel


class MockConfig(BaseModel):
    """Config for mock evaluator."""

    threshold: float = 0.5


class MockTestEvaluator(Evaluator[MockConfig]):
    """Mock evaluator for engine testing."""

    metadata = EvaluatorMetadata(
        name="test-mock-evaluator",
        version="1.0.0",
        description="Test evaluator for engine tests",
    )
    config_model = MockConfig

    async def evaluate(self, data: Any) -> EvaluatorResult:
        """Mock evaluation."""
        value = float(data) if isinstance(data, (int, float)) else 0.0
        matched = value > self.config.threshold

        return EvaluatorResult(
            matched=matched,
            confidence=1.0,
            message=f"Value {value} vs threshold {self.config.threshold}",
            metadata={"value": value, "threshold": self.config.threshold},
        )


class TestEvaluatorArchitecture:
    """Tests verifying the evaluator architecture."""

    def test_evaluator_is_abc_subclass(self):
        """Test Evaluator is an ABC."""
        # Given/When: Checking Evaluator base class
        from abc import ABC

        # Then: Should be subclass of ABC
        assert issubclass(Evaluator, ABC)

    def test_evaluator_has_required_attributes(self):
        """Test evaluators have required class attributes."""
        # Given/When: Checking MockTestEvaluator
        # Then: Should have required attributes
        assert hasattr(MockTestEvaluator, "metadata")
        assert hasattr(MockTestEvaluator, "config_model")
        assert MockTestEvaluator.metadata.name == "test-mock-evaluator"

    def test_evaluator_from_dict(self):
        """Test creating evaluator from dict config."""
        # Given/When: Creating evaluator from dict
        evaluator = MockTestEvaluator.from_dict({"threshold": 0.7})

        # Then: Config should be parsed correctly
        assert isinstance(evaluator.config, MockConfig)
        assert evaluator.config.threshold == 0.7


class TestMockEvaluatorEvaluation:
    """Tests for mock evaluator evaluation."""

    @pytest.fixture(autouse=True)
    def register_mock(self):
        """Register mock evaluator for tests."""
        register_evaluator(MockTestEvaluator)
        yield
        # Don't clear - other tests need built-in evaluators

    @pytest.mark.asyncio
    async def test_evaluate_matched(self):
        """Test evaluation when threshold exceeded."""
        # Given: Mock evaluator with threshold 0.5
        config = EvaluatorSpec(name="test-mock-evaluator", config={"threshold": 0.5})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating value above threshold
        result = await evaluator.evaluate(0.8)

        # Then: Should match with metadata
        assert result.matched is True
        assert result.confidence == 1.0
        assert result.metadata["value"] == 0.8
        assert result.metadata["threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_evaluate_not_matched(self):
        """Test evaluation when below threshold."""
        # Given: Mock evaluator with threshold 0.9
        config = EvaluatorSpec(name="test-mock-evaluator", config={"threshold": 0.9})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating value below threshold
        result = await evaluator.evaluate(0.3)

        # Then: Should not match
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_multiple_evaluations(self):
        """Test multiple evaluations with same evaluator."""
        # Given: Mock evaluator with threshold 0.5
        config = EvaluatorSpec(name="test-mock-evaluator", config={"threshold": 0.5})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating multiple values
        results = [
            await evaluator.evaluate(0.2),
            await evaluator.evaluate(0.6),
            await evaluator.evaluate(0.9),
        ]

        # Then: Results depend on threshold comparison
        assert results[0].matched is False  # 0.2 < 0.5
        assert results[1].matched is True  # 0.6 > 0.5
        assert results[2].matched is True  # 0.9 > 0.5


class TestEvaluatorMetadata:
    """Tests for evaluator metadata."""

    def test_access_metadata(self):
        """Test that evaluator metadata is accessible."""
        # Given/When: Accessing MockTestEvaluator metadata
        # Then: All fields should be correct
