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
