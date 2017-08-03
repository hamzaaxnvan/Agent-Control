"""Tests for the LRU-cached evaluator factory."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from agent_control_evaluators import (
    Evaluator,
    EvaluatorConfig,
    EvaluatorMetadata,
    clear_evaluator_cache,
    clear_evaluators,
    get_all_evaluators,
    get_evaluator_instance,
    register_evaluator,
)
from agent_control_evaluators import _factory as factory_module
from agent_control_models import EvaluatorResult, EvaluatorSpec


class _FactoryConfig(EvaluatorConfig):
    payload: str = "default"


class _FactoryEvaluator(Evaluator[_FactoryConfig]):
    metadata = EvaluatorMetadata(name="factory-dummy", version="1.0.0", description="")
    config_model = _FactoryConfig

    async def evaluate(self, data: Any) -> EvaluatorResult:
        return EvaluatorResult(matched=False, confidence=1.0, message="")


@pytest.fixture
def isolated_factory():
    """Snapshot registry/cache so factory tests don't leak state."""
    snapshot = dict(get_all_evaluators())
    clear_evaluators()
    clear_evaluator_cache()
    register_evaluator(_FactoryEvaluator)
    yield
    clear_evaluator_cache()
