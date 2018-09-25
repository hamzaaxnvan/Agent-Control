"""Tests for @control decorator."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

import httpx
import pytest
from agent_control.control_decorators import ControlSteerError, ControlViolationError, control
from agent_control_telemetry import clear_trace_context_provider, set_trace_context_provider
from pydantic import ValidationError

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = MagicMock()
    agent.agent_name = "550e8400-e29b-41d4-a716-446655440000"
    return agent


@pytest.fixture
def mock_safe_response():
    """Response when evaluation passes."""
    return {
        "is_safe": True,
        "confidence": 1.0,
        "matches": []
    }


@pytest.fixture
def mock_unsafe_response():
    """Response when evaluation fails with deny."""
    return {
        "is_safe": False,
        "confidence": 0.95,
        "matches": [
            {
                "control_id": 1,
                "control_name": "test-control",
                "action": "deny",
                "result": {
                    "matched": True,
                    "confidence": 0.95,
                    "message": "Control triggered: toxicity detected",
                    "metadata": {"score": 0.92}
                }
            }
        ]
    }


@pytest.fixture
def mock_observe_response():
    """Response when evaluation triggers a non-blocking observe action."""
    return {
        "is_safe": False,
        "confidence": 0.7,
        "matches": [
            {
                "control_id": 1,
                "control_name": "observe-control",
                "action": "observe",
                "result": {
                    "matched": True,
                    "message": "Potential issue detected"
                }
            }
        ]
    }


@pytest.fixture
def mock_steer_response():
    """Response when evaluation triggers steer action with steering context."""
    return {
        "is_safe": False,
        "confidence": 0.85,
        "matches": [
            {
                "control_id": 2,
                "control_name": "steer-control",
                "action": "steer",
                "steering_context": {
                    "message": "Please rephrase your question using respectful language"
                },
                "result": {
                    "matched": True,
                    "message": "Inappropriate language detected",
                    "metadata": {"pattern": "offensive_word"}
                }
            }
        ]
    }


# =============================================================================
# BASIC FUNCTIONALITY TESTS
# =============================================================================

class TestControl:
    """Tests for @control decorator."""

    @pytest.mark.asyncio
    async def test_passes_when_safe(self, mock_agent, mock_safe_response):
        """Test that safe evaluation allows function execution."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=mock_safe_response):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            result = await chat("Hello!")
            assert result == "Response to: Hello!"

    @pytest.mark.asyncio
    async def test_blocks_when_unsafe(self, mock_agent, mock_unsafe_response):
        """Test that unsafe evaluation blocks with ControlViolationError."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=mock_unsafe_response):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            with pytest.raises(ControlViolationError) as exc_info:
                await chat("Toxic message")

            assert exc_info.value.control_name == "test-control"
            assert "toxicity" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_observes_without_blocking(self, mock_agent, mock_observe_response, caplog):
        """Test that observe action logs but allows execution."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=mock_observe_response):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            result = await chat("Questionable message")
            assert result == "Response to: Questionable message"

    @pytest.mark.asyncio
    async def test_legacy_warn_action_observes_without_blocking(self, mock_agent):
        """Legacy advisory actions from older servers should be treated as observe."""
        legacy_observe_response = {
            "is_safe": False,
            "confidence": 0.7,
            "matches": [
                {
                    "control_id": 1,
                    "control_name": "legacy-observe-control",
                    "action": "warn",
                    "result": {
                        "matched": True,
                        "message": "Potential issue detected"
                    }
                }
            ]
        }
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=legacy_observe_response), \
             patch("agent_control.control_decorators.logger") as mock_logger:

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            result = await chat("Questionable legacy message")

            assert result == "Response to: Questionable legacy message"
            mock_logger.info.assert_any_call(
                "Control observe [legacy-observe-control]: Potential issue detected"
            )

    @pytest.mark.asyncio
    async def test_no_agent_runs_without_protection(self):
        """Test that decorator passes through if no agent initialized."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=None):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            result = await chat("Hello!")
            assert result == "Response to: Hello!"

    @pytest.mark.asyncio
    async def test_explicit_step_type_is_used_for_pre_and_post_payloads(
        self, mock_agent, mock_safe_response
    ):
        """Explicit custom types reach both decorator evaluation stages."""
        payloads = []

        async def mock_evaluate(*args, **kwargs):
            payloads.append(args[1])
            return mock_safe_response

        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", side_effect=mock_evaluate):

            @control(step_name="retrieve_documents", step_type=" retriever ")
            async def retrieve(query: str, top_k: int, filters: dict[str, str]) -> str:
                return query

            await retrieve("hello", 5, {"language": "en"})

        assert [payload["type"] for payload in payloads] == ["retriever", "retriever"]
        assert payloads[0]["name"] == "retrieve_documents"
        assert payloads[0]["input"] == {
            "query": "hello",
            "top_k": 5,
            "filters": {"language": "en"},
        }

    @pytest.mark.asyncio
    async def test_omitted_tools_preserves_legacy_payload(self, mock_agent, mock_safe_response):
        payloads = []

        async def capture_payload(*args, **kwargs):
            payloads.append(args[1])
            return mock_safe_response

        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate", side_effect=capture_payload),
        ):

            @control()
            async def answer(message: str) -> str:
                return "answer"

            await answer("question")

        assert payloads == [
            {"type": "llm", "name": "answer", "input": "question", "output": None},
            {"type": "llm", "name": "answer", "input": "question", "output": "answer"},
        ]

    @pytest.mark.asyncio
    async def test_static_tools_are_copied_into_pre_and_post_payloads(
        self, mock_agent, mock_safe_response
    ):
        original_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search documents",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
            }
        ]
        expected_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search documents",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
            }
        ]
        payloads = []

        async def capture_payload(*args, **kwargs):
            payload = args[1]
            payloads.append(
                {
                    "type": payload["type"],
                    "name": payload["name"],
                    "input": payload["input"],
                    "output": payload["output"],
                    "tools": deepcopy(payload["tools"]),
                }
            )
            payload["tools"][0]["function"]["parameters"]["properties"]["query"][
                "type"
            ] = "integer"
            return mock_safe_response

        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate", side_effect=capture_payload),
        ):
            @control(tools=original_tools)
            async def answer(message: str) -> str:
                return "answer"

            original_tools[0]["function"]["description"] = "caller mutation"
            await answer("question")

        assert [payload["tools"] for payload in payloads] == [expected_tools, expected_tools]
        assert original_tools[0]["function"]["description"] == "caller mutation"
        assert original_tools[0]["function"]["parameters"]["properties"]["query"][
            "type"
        ] == "string"

    @pytest.mark.asyncio
    async def test_dynamic_tools_receive_call_arguments(self, mock_agent, mock_safe_response):
        calls = []
        payloads = []
        available_tools = [{"name": "lookup", "parameters": {"type": "object"}}]

        def provide_tools(args, kwargs):
            calls.append((args, dict(kwargs)))
            return available_tools

        async def capture_payload(*args, **kwargs):
            payloads.append(args[1])
            return mock_safe_response

        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate", side_effect=capture_payload),
        ):

            @control(tools=provide_tools)
            async def answer(message: str, *, language: str) -> str:
                return "answer"

            await answer("question", language="en")

        assert calls == [
            (("question",), {"language": "en"}),
