"""Tests for entry-point-based evaluator discovery."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_control_evaluators import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorMetadata,
    clear_evaluators,
    discover_evaluators,
    ensure_evaluators_discovered,
    get_all_evaluators,
    list_evaluators,
    register_evaluator,
    reset_evaluator_discovery,
)
from agent_control_evaluators import _discovery as discovery_module
from agent_control_models import EvaluatorResult


class _DiscoveryConfig(EvaluatorConfig):
    pass


def _make_class(*, name: str, available: bool = True) -> type[Evaluator[_DiscoveryConfig]]:
    class _Dummy(Evaluator[_DiscoveryConfig]):
        metadata = EvaluatorMetadata(name=name, version="1.0.0", description="")
        config_model = _DiscoveryConfig

        @classmethod
        def is_available(cls) -> bool:
            return available

        async def evaluate(self, data: Any) -> EvaluatorResult:
            return EvaluatorResult(matched=False, confidence=1.0, message="")

    _Dummy.__name__ = f"Discovery_{name.replace('-', '_')}"
    return _Dummy


@pytest.fixture
def isolated_discovery():
    """Snapshot registry + discovery flag, restore on teardown."""
    snapshot = dict(get_all_evaluators())
    clear_evaluators()
    reset_evaluator_discovery()
    yield
    clear_evaluators()
    reset_evaluator_discovery()
    for cls in snapshot.values():
        register_evaluator(cls)


def _make_fake_entry_point(name: str, evaluator_class: type[Any]) -> MagicMock:
    """Build a MagicMock that mimics importlib.metadata.EntryPoint."""
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = evaluator_class
    return ep


def test_discover_evaluators_registers_available_classes(isolated_discovery):
    """Discover walks the entry-point group and registers each available class."""
    cls = _make_class(name="disc-a")
    fake_ep = _make_fake_entry_point("disc-a", cls)

    with patch.object(discovery_module, "entry_points", return_value=[fake_ep]):
        count = discover_evaluators()

    assert count == 1
    assert get_all_evaluators().get("disc-a") is cls


def test_discover_evaluators_skips_unavailable_classes(isolated_discovery):
    """Evaluators whose is_available() is False must NOT be registered."""
    cls = _make_class(name="disc-unavailable", available=False)
    fake_ep = _make_fake_entry_point("disc-unavailable", cls)

    with patch.object(discovery_module, "entry_points", return_value=[fake_ep]):
        count = discover_evaluators()

    assert count == 0
    assert "disc-unavailable" not in get_all_evaluators()


def test_discover_evaluators_skips_already_registered(isolated_discovery):
    """Already-registered names are skipped without raising."""
    cls = _make_class(name="disc-existing")
    register_evaluator(cls)
