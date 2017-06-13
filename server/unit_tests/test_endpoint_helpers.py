"""Unit tests for endpoint helpers that don't require the DB test fixture."""

from types import SimpleNamespace

from agent_control_models import ControlDefinition, ControlMatch, EvaluatorResult
from agent_control_server.endpoints.agents import (
    _find_referencing_controls_for_removed_evaluators,
)
from agent_control_server.endpoints.evaluation import (
    ControlAdapter,
    _sanitize_control_match,
)


def test_find_referencing_controls_dedupes_composite_matches() -> None:
    # Given: two leaves in the same control reference the same evaluator
    controls = [
        SimpleNamespace(
            name="composite-ctrl",
            control=ControlDefinition(
