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
