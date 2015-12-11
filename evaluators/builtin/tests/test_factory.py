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
    clear_evaluators()
    for cls in snapshot.values():
        register_evaluator(cls)


def test_get_evaluator_instance_returns_evaluator(isolated_factory):
    spec = EvaluatorSpec(name="factory-dummy", config={"payload": "p1"})

    instance = get_evaluator_instance(spec)

    assert isinstance(instance, _FactoryEvaluator)
    assert instance.config.payload == "p1"


def test_get_evaluator_instance_caches_by_config(isolated_factory):
    spec_a = EvaluatorSpec(name="factory-dummy", config={"payload": "same"})
    spec_b = EvaluatorSpec(name="factory-dummy", config={"payload": "same"})

    first = get_evaluator_instance(spec_a)
    second = get_evaluator_instance(spec_b)

    # Same config = same cached instance.
    assert first is second


def test_get_evaluator_instance_treats_different_configs_separately(isolated_factory):
    spec_a = EvaluatorSpec(name="factory-dummy", config={"payload": "a"})
    spec_b = EvaluatorSpec(name="factory-dummy", config={"payload": "b"})

    instance_a = get_evaluator_instance(spec_a)
    instance_b = get_evaluator_instance(spec_b)

    assert instance_a is not instance_b
    assert instance_a.config.payload == "a"
    assert instance_b.config.payload == "b"


def test_get_evaluator_instance_raises_for_unknown_evaluator(isolated_factory):
    with pytest.raises(ValueError, match="not found"):
        get_evaluator_instance(EvaluatorSpec(name="no-such-evaluator", config={}))


def test_clear_evaluator_cache_forces_recreation(isolated_factory):
