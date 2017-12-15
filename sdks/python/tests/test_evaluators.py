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
        """Test creating evaluator metadata."""
        metadata = EvaluatorMetadata(
            name="test-evaluator",
            version="1.0.0",
            description="Test evaluator",
        )

        assert metadata.name == "test-evaluator"
        assert metadata.version == "1.0.0"
        assert metadata.description == "Test evaluator"
        assert metadata.requires_api_key is False
        assert metadata.timeout_ms == 10000  # Default

    def test_metadata_with_all_fields(self):
        """Test metadata with all fields populated."""
        metadata = EvaluatorMetadata(
            name="full-evaluator",
            version="2.0.0",
            description="Full test",
            requires_api_key=True,
            timeout_ms=5000,
        )

        assert metadata.requires_api_key is True
        assert metadata.timeout_ms == 5000


class TestEvaluatorRegistry:
    """Tests for evaluator registry functionality."""

    def setup_method(self):
        """Clear registry before each test."""
        # Clear all evaluators and reset discovery
        clear_evaluators()
        reset_evaluator_discovery()
        # Run discovery to load built-in evaluators
        discover_evaluators()

    def test_register_evaluator(self):
        """Test registering an evaluator."""
        # Register mock evaluator
        register_evaluator(MockEvaluator)

        # Verify it's registered
        evaluator_class = list_evaluators().get("test-mock-evaluator")
        assert evaluator_class is MockEvaluator

    def test_get_nonexistent_evaluator(self):
        """Test getting an evaluator that doesn't exist."""
        evaluator_class = list_evaluators().get("nonexistent-evaluator-xyz")
        assert evaluator_class is None

    def test_list_evaluators_includes_registered(self):
        """Test listing evaluators includes registered evaluators."""
        # Register mock evaluator
        register_evaluator(MockEvaluator)

        # List evaluators - now returns dict of evaluator classes
        evaluators = list_evaluators()

        assert "test-mock-evaluator" in evaluators
        assert evaluators["test-mock-evaluator"] is MockEvaluator

    def test_builtin_evaluators_available(self):
        """Test that built-in evaluators are available after discovery."""
        evaluators = list_evaluators()

        assert "regex" in evaluators
        assert "list" in evaluators

    def test_register_duplicate_evaluator_raises_error(self):
        """Test that registering a different evaluator with same name raises ValueError."""
        # Register evaluator first
        register_evaluator(MockEvaluator)

        # Create a different class with the same evaluator name
        class DuplicateEvaluator(Evaluator):
            metadata = EvaluatorMetadata(
                name="test-mock-evaluator",  # Same name as MockEvaluator
                version="2.0.0",
                description="Duplicate evaluator",
            )
            config_model = MockConfig

            def evaluate(self, data) -> EvaluatorResult:
                return EvaluatorResult(matched=False, confidence=1.0, message="duplicate")

        # Second registration with different class should fail
        with pytest.raises(ValueError, match="already registered"):
            register_evaluator(DuplicateEvaluator)

    def test_re_register_same_evaluator_allowed(self):
        """Test that re-registering the same class is allowed (hot reload support)."""
        register_evaluator(MockEvaluator)
        # Should not raise - same class can be re-registered
        result = register_evaluator(MockEvaluator)
        assert result is MockEvaluator


class TestEvaluatorBase:
    """Tests for Evaluator base class."""

    def test_evaluator_evaluate(self):
        """Test synchronous evaluation."""
        # Config is now passed at init
        evaluator = MockEvaluator({"threshold": 0.5})
        result = evaluator.evaluate(data=0.8)

        assert isinstance(result, EvaluatorResult)
        assert result.matched is True
        assert result.confidence == 1.0
        assert "Mock evaluation" in result.message

    def test_evaluator_evaluate_no_match(self):
        """Test evaluation when rule doesn't match."""
        evaluator = MockEvaluator({"threshold": 0.5})
        result = evaluator.evaluate(data=0.3)

        assert isinstance(result, EvaluatorResult)
        assert result.matched is False
        assert result.confidence == 1.0

    def test_evaluator_with_different_configs(self):
        """Test evaluator uses config correctly (set at init)."""
        # Create two evaluators with different configs
        evaluator_low = MockEvaluator({"threshold": 0.5})
        evaluator_high = MockEvaluator({"threshold": 0.7})

        # Same data, different thresholds
        assert evaluator_low.evaluate(data=0.6).matched is True
