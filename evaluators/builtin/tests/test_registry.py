"""Tests for the in-memory evaluator registry."""

from __future__ import annotations

from typing import Any

import pytest
from agent_control_evaluators import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorMetadata,
    clear_evaluators,
    get_all_evaluators,
    get_evaluator,
    register_evaluator,
)
from agent_control_models import EvaluatorResult


class _DummyConfig(EvaluatorConfig):
    pass


def _make_class(*, name: str, available: bool = True) -> type[Evaluator[_DummyConfig]]:
    """Build a fresh Evaluator subclass with the supplied metadata name."""

    class _Dummy(Evaluator[_DummyConfig]):
        metadata = EvaluatorMetadata(
            name=name,
            version="1.0.0",
            description="",
        )
        config_model = _DummyConfig

        @classmethod
        def is_available(cls) -> bool:
            return available

        async def evaluate(self, data: Any) -> EvaluatorResult:
            return EvaluatorResult(matched=False, confidence=1.0, message="")

    _Dummy.__name__ = f"Dummy_{name.replace('-', '_')}"
    return _Dummy


@pytest.fixture
def isolated_registry():
    """Snapshot and restore the global registry so tests don't leak state."""
    snapshot = dict(get_all_evaluators())
    clear_evaluators()
    yield
    clear_evaluators()
    for cls in snapshot.values():
        register_evaluator(cls)


def test_register_and_lookup_evaluator(isolated_registry):
    cls = _make_class(name="reg-a")

