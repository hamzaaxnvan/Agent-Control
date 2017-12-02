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
        """Test graceful handling of evaluator load errors."""
        mock_ep = MagicMock()
        mock_ep.name = "bad-evaluator"
        mock_ep.load.side_effect = ImportError("Missing dependency")
        mock_entry_points.return_value = [mock_ep]

        # Should not raise
        discover_evaluators()

    def test_discover_evaluators_only_runs_once(self) -> None:
        """Test that discovery only runs once."""
        count1 = discover_evaluators()
        count2 = discover_evaluators()

        # First call loads evaluators, second call returns 0 (already discovered)
        assert count2 == 0
        # Verify evaluators are available (count may be 0 if no entry-point evaluators)
        evaluators = list_evaluators()
        assert "regex" in evaluators
        assert "list" in evaluators

    def test_ensure_evaluators_discovered_triggers_discovery(self) -> None:
        """Test that ensure_evaluators_discovered triggers discovery."""
        ensure_evaluators_discovered()

        evaluators = list_evaluators()
        # Should have at least built-in evaluators
        assert isinstance(evaluators, dict)
        assert "regex" in evaluators
        assert "list" in evaluators

    def test_reset_evaluator_discovery_allows_rediscovery(self) -> None:
        """Test that reset_evaluator_discovery allows discovery to run again."""
        discover_evaluators()
        evaluators1 = list_evaluators()
        assert "regex" in evaluators1

        # After reset, discovery should run again
        reset_evaluator_discovery()
        clear_evaluators()

        discover_evaluators()
        evaluators2 = list_evaluators()
        assert "regex" in evaluators2
        assert "list" in evaluators2

    @patch("agent_control_evaluators._discovery.entry_points")
    def test_discover_evaluators_skips_unavailable(
        self, mock_entry_points: MagicMock
    ) -> None:
        """Test that evaluators with is_available() returning False are skipped."""

        class MockConfig(BaseModel):
            pass

        class UnavailableEvaluator(Evaluator[MockConfig]):
            metadata = EvaluatorMetadata(
                name="unavailable-evaluator",
                version="1.0.0",
                description="Evaluator with missing deps",
            )
            config_model = MockConfig

            @classmethod
            def is_available(cls) -> bool:
                return False  # Simulate missing dependency

            async def evaluate(self, data: Any) -> EvaluatorResult:
                return EvaluatorResult(matched=False, confidence=0.0, message="test")

        mock_ep = MagicMock()
        mock_ep.name = "unavailable-evaluator"
