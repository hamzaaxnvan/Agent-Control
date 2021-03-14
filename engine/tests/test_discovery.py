"""Tests for evaluator auto-discovery."""

from typing import Any
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from agent_control_engine import (
    discover_evaluators,
    ensure_evaluators_discovered,
    list_evaluators,
    reset_evaluator_discovery,
)
from agent_control_evaluators import (
    Evaluator,
    EvaluatorMetadata,
    clear_evaluators,
    get_evaluator,
    register_evaluator,
)
from agent_control_models import EvaluatorResult


class TestDiscoverEvaluators:
    """Tests for discover_evaluators() function."""

    def test_discover_evaluators_loads_builtins(self) -> None:
        """Test that built-in evaluators are loaded."""
        discover_evaluators()

        evaluators = list_evaluators()
        assert "regex" in evaluators
        assert "list" in evaluators

    @patch("agent_control_evaluators._discovery.entry_points")
    def test_discover_evaluators_loads_entry_points(
        self, mock_entry_points: MagicMock
    ) -> None:
        """Test that entry point evaluators are discovered."""

        # Create mock evaluator
        class MockConfig(BaseModel):
            pass

        class MockEvaluator(Evaluator[MockConfig]):
            metadata = EvaluatorMetadata(
                name="mock-ep-evaluator",
                version="1.0.0",
                description="Test evaluator",
            )
            config_model = MockConfig

            async def evaluate(self, data: Any) -> EvaluatorResult:
                return EvaluatorResult(matched=False, confidence=0.0, message="test")

        mock_ep = MagicMock()
        mock_ep.name = "mock-ep-evaluator"
        mock_ep.load.return_value = MockEvaluator
        mock_entry_points.return_value = [mock_ep]

        count = discover_evaluators()

        mock_entry_points.assert_called_once_with(group="agent_control.evaluators")
        evaluators = list_evaluators()
        assert "mock-ep-evaluator" in evaluators
        # Count only includes entry-point registrations (not built-ins loaded via import)
        assert count >= 1

    @patch("agent_control_evaluators._discovery.entry_points")
    def test_discover_evaluators_handles_load_error(
        self, mock_entry_points: MagicMock
    ) -> None:
