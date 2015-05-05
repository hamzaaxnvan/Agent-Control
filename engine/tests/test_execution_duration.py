"""Public engine contract tests for per-control execution durations."""

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from unittest.mock import AsyncMock, Mock

import pytest
from agent_control_engine.core import ControlEngine
from agent_control_evaluators import Evaluator, EvaluatorMetadata, register_evaluator
from agent_control_models import ControlDefinition, EvaluationRequest, EvaluatorResult, Step
from pydantic import BaseModel


class DurationConfig(BaseModel):
    matched: bool = False
    raises_error: bool = False
    blocks: bool = False


class DurationEvaluator(Evaluator[DurationConfig]):
    metadata = EvaluatorMetadata(
        name="test-duration",
        version="1.0.0",
        description="Returns a configured outcome or waits for cancellation",
    )
    config_model = DurationConfig

    async def evaluate(self, data: Any) -> EvaluatorResult:
        # Yield once so concurrent controls all start before one completes.
        await asyncio.sleep(0)
        if self.config.blocks:
            await asyncio.Event().wait()
        if self.config.raises_error:
            raise RuntimeError("evaluation failed")
        return EvaluatorResult(matched=self.config.matched, confidence=1.0)


@dataclass
class DurationControl:
    id: int
    name: str
    control: ControlDefinition


@pytest.fixture(autouse=True)
def register_duration_evaluator() -> None:
    register_evaluator(DurationEvaluator)


@pytest.fixture
def evaluation_request() -> EvaluationRequest:
    return EvaluationRequest(
        agent_name="duration-test-agent",
        step=Step(type="llm", name="test-step", input="test", output=None),
        stage="pre",
    )


def make_control(
    control_id: int = 1,
    *,
    context: Literal["server", "sdk"] = "server",
    matched: bool = False,
    raises_error: bool = False,
    blocks: bool = False,
    decision: Literal["observe", "deny"] = "observe",
) -> DurationControl:
    return DurationControl(
        id=control_id,
        name=f"duration-control-{control_id}",
        control=ControlDefinition(
            description="Duration test control",
            enabled=True,
            execution=context,
            scope={"stages": ["pre"], "step_types": ["llm"]},
            condition={
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "test-duration",
                    "config": {
                        "matched": matched,
                        "raises_error": raises_error,
                        "blocks": blocks,
                    },
                },
            },
            action={"decision": decision},
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["server", "sdk"])
@pytest.mark.parametrize("category", ["matches", "non_matches", "errors"])
@pytest.mark.parametrize("elapsed_seconds", [0.0, 0.0125])
async def test_completed_controls_report_elapsed_milliseconds(
    monkeypatch: pytest.MonkeyPatch,
    evaluation_request: EvaluationRequest,
    context: Literal["server", "sdk"],
    category: str,
    elapsed_seconds: float,
) -> None:
    # Given: a completed control and a controlled clock instead of wall-clock assertions
    control = make_control(
        context=context,
        matched=category == "matches",
        raises_error=category == "errors",
    )
    clock = Mock(side_effect=[10.0, 10.0 + elapsed_seconds])
    monkeypatch.setattr("agent_control_engine.core.time.perf_counter", clock)

    # When: evaluating via the public engine entrypoint
    response = await ControlEngine([control], context=context).process(evaluation_request)

    # Then: all completed outcome categories retain their own duration, including zero
    results = getattr(response, category)
    assert results is not None
    assert len(results) == 1
    assert results[0].execution_duration_ms == pytest.approx(elapsed_seconds * 1000)
    assert results[0].result.matched is (category == "matches")
    assert bool(results[0].result.error) is (category == "errors")
    assert response.is_safe is True


@pytest.mark.asyncio
async def test_parallel_controls_keep_individual_durations(
