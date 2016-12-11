"""Tests for StepRecorder, the incremental Step tree builder."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from agent_control_models import EvaluationResult, Step

from agent_control import record_step, step_recorder
from agent_control.control_decorators import _create_evaluation_payload


def test_nested_trace_builds_expected_step():
    """A trace with span children and a leaf retriever builds the matching tree."""
    with record_step("trace", "banking_trace", input={"request": "r1"}) as trace:
        with trace.child("retriever", "policy_lookup", input="refund policy?") as retriever:
            retriever.output = {"hits": 1}
        trace.output = {"status": "planned"}

    step = trace.build()

    assert step.type == "trace"
    assert step.name == "banking_trace"
    assert step.input == {"request": "r1"}
    assert step.output == {"status": "planned"}
    assert step.children is not None
    assert len(step.children) == 1
    child = step.children[0]
    assert child.type == "retriever"
    assert child.name == "policy_lookup"
    assert child.input == "refund policy?"
    assert child.output == {"hits": 1}


def test_session_nests_traces():
    """Sessions nest traces the same way traces nest spans."""
    with record_step("session", "banking_session") as session:
        with session.child("trace", "turn_1") as trace:
            with trace.child("llm", "respond") as llm:
                llm.output = "hi"

    step = session.build()

    assert step.type == "session"
    assert len(step.children) == 1
    assert step.children[0].type == "trace"
    assert step.children[0].name == "turn_1"
    assert len(step.children[0].children) == 1
    assert step.children[0].children[0].type == "llm"


def test_call_matches_decorator_payload_for_tool():
    """StepRecorder.call() must capture the same payload _create_evaluation_payload would."""

    def lookup_account(account_id: str) -> dict:
        return {"balance": 100}

    with record_step("trace", "t") as trace:
        result = trace.call(
            lookup_account, account_id="acct-1", step_type="tool", step_name="lookup_account"
        )

    assert result == {"balance": 100}
    expected_payload = _create_evaluation_payload(
        lookup_account, (), {"account_id": "acct-1"}, result, "lookup_account", "tool", None
    )
    [child] = trace.build().children
    assert child.model_dump(exclude_none=True) == {
        k: v for k, v in expected_payload.items() if v is not None
    }


@pytest.mark.asyncio
async def test_acall_runs_async_function_and_records_child():
    """StepRecorder.acall() awaits the function and records the result."""

    async def run_banking_model(prompt: str) -> str:
        return f"answer: {prompt}"

    with record_step("trace", "t") as trace:
        result = await trace.acall(
            run_banking_model, "hello", step_type="llm", step_name="respond"
        )

    assert result == "answer: hello"
    [child] = trace.build().children
    assert child.type == "llm"
    assert child.name == "respond"
    assert child.input == "hello"
    assert child.output == "answer: hello"


def test_call_step_context_is_recorded():
    """step_context is merged into the recorded child's context."""

    def lookup_account(account_id: str) -> dict:
        return {"balance": 100}

    with record_step("trace", "t") as trace:
        trace.call(
            lookup_account,
            account_id="acct-1",
            step_type="tool",
            step_name="lookup_account",
            step_context={"executed_function": "lookup_account"},
        )

    [child] = trace.build().children
    assert child.context == {"executed_function": "lookup_account"}


def test_call_step_context_does_not_collide_with_func_context_kwarg():
    """step_context is merged into Step.context, not forwarded to func - a plain
    `context` kwarg on call() would instead be swallowed by **kwargs and sent
    to func, silently dropping the caller's intended Step metadata."""

    received: dict[str, Any] = {}

    def run_banking_model(prompt: str, *, context: dict[str, Any] | None = None) -> str:
        received["context"] = context
        return f"answer: {prompt}"

    with record_step("trace", "t") as trace:
        result = trace.call(
            run_banking_model,
            "hello",
            context={"account": "acct-1"},
            step_type="llm",
            step_name="respond",
            step_context={"executed_function": "run_banking_model"},
        )

    assert result == "answer: hello"
    assert received["context"] == {"account": "acct-1"}
    [child] = trace.build().children
    assert child.context == {"executed_function": "run_banking_model"}


def test_call_step_context_and_error_merge_on_failure():
    """On failure, the error key is added to step_context's dict and wins on collision."""

    def flaky(x: int) -> int:
        raise ValueError("boom")

    with record_step("trace", "t") as trace:
        with pytest.raises(ValueError, match="boom"):
            trace.call(
                flaky,
                1,
                step_type="tool",
                step_name="flaky",
                step_context={"attempt": 1, "error": "overwritten"},
            )

    [child] = trace.build().children
    assert child.context == {"attempt": 1, "error": "ValueError('boom')"}


def test_call_records_exception_and_reraises():
    """A failing call is still recorded as a child (with the error in context), then re-raised."""

    def flaky(x: int) -> int:
        raise ValueError("boom")

    with record_step("trace", "t") as trace:
        with pytest.raises(ValueError, match="boom"):
            trace.call(flaky, 1, step_type="tool", step_name="flaky")

    [child] = trace.build().children
    assert child.name == "flaky"
    assert child.output is None
    assert child.context == {"error": "ValueError('boom')"}


@pytest.mark.asyncio
async def test_acall_records_exception_and_reraises():
    """acall()'s failure path mirrors call(): record (error in context), then re-raise."""

    async def flaky(x: int) -> int:
        raise ValueError("boom")

    with record_step("trace", "t") as trace:
        with pytest.raises(ValueError, match="boom"):
            await trace.acall(flaky, 1, step_type="tool", step_name="flaky")

    [child] = trace.build().children
    assert child.name == "flaky"
