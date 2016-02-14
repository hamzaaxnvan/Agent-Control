"""Tests for check_evaluation behavior."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from agent_control_models import Step
from pydantic import ValidationError

from agent_control import evaluation
from agent_control.evaluation import EvaluationResult


@pytest.mark.asyncio
async def test_check_evaluation_requires_step_name_before_server_call():
    """Typed request validation should reject steps without a name before server call."""

    client = MagicMock()
    client.http_client = AsyncMock()
    client.http_client.post = AsyncMock()

    with pytest.raises(ValidationError):
        await evaluation.check_evaluation(
            client=client,
            agent_name=UUID("00000000-0000-0000-0000-000000000001"),
            step={"type": "llm", "input": "hello"},
            stage="pre",
        )

    client.http_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_check_evaluation_returns_result_model():
    """check_evaluation returns a parsed EvaluationResult."""
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"is_safe": True, "confidence": 0.75, "reason": "ok"}

    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.post = AsyncMock(return_value=DummyResponse())

    result = await evaluation.check_evaluation(
        client=client,
        agent_name="Agent-Example_01",
        step={"type": "llm", "name": "chat", "input": "hello"},
        stage="pre",
    )

    assert result.is_safe is True
    assert result.confidence == 0.75
    assert result.reason == "ok"
    client.http_client.post.assert_awaited_once_with(
        "/api/v1/evaluation",
        json={
            "agent_name": "agent-example_01",
            "step": {
                "type": "llm",
                "name": "chat",
                "input": "hello",
                    "output": None,
                    "context": None,
                    "tools": None,
                    "ground_truth": None,
            },
            "stage": "pre",
            "target_type": None,
            "target_id": None,
        },
        headers=None,
    )


@pytest.mark.asyncio
async def test_check_evaluation_sends_custom_step_type_to_server():
    """The server path sends one generic Step inside EvaluationRequest."""

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"is_safe": True, "confidence": 1.0}

    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.post = AsyncMock(return_value=DummyResponse())

    await evaluation.check_evaluation(
        client=client,
        agent_name="Agent-Example_01",
        step={"type": "trace", "name": "trace-check", "input": "hello"},
        stage="post",
    )

    request = client.http_client.post.await_args.kwargs["json"]
    assert request["step"] == {
        "type": "trace",
        "name": "trace-check",
        "input": "hello",
        "output": None,
        "context": None,
        "tools": None,
        "ground_truth": None,
    }


@pytest.mark.asyncio
async def test_check_evaluation_accepts_step_with_tool_definitions():
    """Framework callers can send a fully structured Step directly."""

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"is_safe": True, "confidence": 1.0}

    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.post = AsyncMock(return_value=DummyResponse())
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]
    step = Step(
        type="llm",
        name="openai_agent",
        input=[{"role": "user", "content": "question"}],
        output={"role": "assistant", "content": "answer"},
        tools=tools,
    )

    await evaluation.check_evaluation(
        client=client,
        agent_name="Agent-Example_01",
        step=step,
        stage="post",
    )

    sent_step = client.http_client.post.await_args.kwargs["json"]["step"]
    assert sent_step["tools"] == tools
    assert sent_step["tools"][0]["function"]["parameters"]["properties"]["query"] == {
        "type": "string"
    }


@pytest.mark.asyncio
async def test_evaluate_controls_requires_server_url():
    """evaluate_controls should require server_url to be configured."""
    with patch("agent_control.state.server_url", None):
        with pytest.raises(RuntimeError, match="Server URL not configured"):
            await evaluation.evaluate_controls(
                step_name="chat",
                input="hello",
                stage="pre",
                agent_name="test-bot",
            )


@pytest.mark.asyncio
async def test_evaluate_controls_with_explicit_agent_name(monkeypatch):
    """evaluate_controls should call check_evaluation_with_local."""
    mock_result = EvaluationResult(is_safe=True, confidence=1.0)
    mock_check = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(evaluation, "check_evaluation_with_local", mock_check)

    with patch("agent_control.state.server_url", "http://localhost:8000"):
        with patch("agent_control.state.api_key", None):
            result = await evaluation.evaluate_controls(
                step_name="chat",
                input="hello",
                stage="pre",
                agent_name="test-bot",
            )

    assert result.is_safe is True
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_evaluate_controls_delegates_to_evaluate_step(monkeypatch):
    """evaluate_controls builds the Step then routes through evaluate_step."""
    mock_result = EvaluationResult(is_safe=True, confidence=1.0)
    mock_evaluate_step = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(evaluation, "evaluate_step", mock_evaluate_step)

    result = await evaluation.evaluate_controls(
        step_name="chat",
        input="hello",
        stage="pre",
        agent_name="test-bot",
    )

    assert result is mock_result
    mock_evaluate_step.assert_awaited_once()
    args, kwargs = mock_evaluate_step.call_args
    step_arg = args[0]
    assert isinstance(step_arg, Step)
    assert step_arg.name == "chat"
    assert step_arg.input == "hello"
    assert kwargs["agent_name"] == "test-bot"
    assert kwargs["stage"] == "pre"


@pytest.mark.asyncio
async def test_evaluate_controls_coerces_dict_children_to_step(monkeypatch):
    """children= accepts plain dicts; pydantic coerces them to Step instances."""
    mock_check = AsyncMock(return_value=EvaluationResult(is_safe=True, confidence=1.0))
    monkeypatch.setattr(evaluation, "check_evaluation_with_local", mock_check)

    with patch("agent_control.state.server_url", "http://localhost:8000"):
        await evaluation.evaluate_controls(
            step_name="trace1",
            step_type="trace",
            input={"request": "r1"},
            children=[{"type": "llm", "name": "x", "input": "hi", "output": "bye"}],
            stage="post",
            agent_name="test-bot",
        )

    step = mock_check.call_args.kwargs["step"]
    assert step.children is not None
    assert len(step.children) == 1
    assert isinstance(step.children[0], Step)
    assert step.children[0].type == "llm"
    assert step.children[0].name == "x"
    mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_controls_with_context(monkeypatch):
    """evaluate_controls should pass context through to evaluation."""
    mock_result = EvaluationResult(is_safe=True, confidence=1.0)
    mock_check = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(evaluation, "check_evaluation_with_local", mock_check)
