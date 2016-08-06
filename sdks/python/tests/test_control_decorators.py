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
            (("question",), {"language": "en"}),
        ]
        assert payloads[0]["tools"] == available_tools
        assert payloads[1]["tools"] == available_tools

    @pytest.mark.asyncio
    async def test_dynamic_tool_provider_can_return_none(self, mock_agent, mock_safe_response):
        payloads = []

        async def capture_payload(*args, **kwargs):
            payloads.append(args[1])
            return mock_safe_response

        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate", side_effect=capture_payload),
        ):

            @control(tools=lambda args, kwargs: None)
            async def answer(message: str) -> str:
                return "answer"

            await answer("question")

        assert all("tools" not in payload for payload in payloads)

    @pytest.mark.asyncio
    async def test_invalid_tool_definitions_use_step_validation(
        self, mock_agent
    ):
        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate") as mock_evaluate,
        ):

            @control(tools=[{"name": "invalid", "schema": object()}])
            async def answer(message: str) -> str:
                return "should not run"

            with pytest.raises(RuntimeError) as exc_info:
                await answer("question")

        assert isinstance(exc_info.value.__cause__, ValidationError)
        assert "tools" in str(exc_info.value.__cause__)
        mock_evaluate.assert_not_called()

    @pytest.mark.parametrize("step_type", ["tool", "retriever"])
    @pytest.mark.asyncio
    async def test_tools_are_rejected_for_non_llm_steps(
        self, mock_agent, step_type
    ):
        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate") as mock_evaluate,
        ):

            @control(step_type=step_type, tools=[])
            async def answer(message: str) -> str:
                return "should not run"

            with pytest.raises(ValueError, match="requires an LLM step"):
                await answer("question")

        mock_evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_dynamic_tool_provider_failure_blocks_execution(self, mock_agent):
        executed = False

        def provider(args, kwargs):
            raise ValueError("provider failed")

        with (
            patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent),
            patch("agent_control.control_decorators._evaluate") as mock_evaluate,
        ):

            @control(tools=provider)
            async def answer(message: str) -> str:
                nonlocal executed
                executed = True
                return "answer"

            with pytest.raises(RuntimeError, match="Execution blocked for safety") as exc_info:
                await answer("question")

        assert str(exc_info.value.__cause__) == "provider failed"
        assert executed is False
        mock_evaluate.assert_not_called()

    def test_explicit_step_type_overrides_tool_inference(
        self, mock_agent, mock_safe_response
    ):
        """An explicit LLM type wins even when function metadata looks like a tool."""
        payloads = []

        async def mock_evaluate(*args, **kwargs):
            payloads.append(args[1])
            return mock_safe_response

        def search(query: str) -> str:
            return query

        search.name = "search"  # type: ignore[attr-defined]

        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", side_effect=mock_evaluate):
            guarded_search = control(step_type="llm")(search)
            guarded_search("hello")

        assert [payload["type"] for payload in payloads] == ["llm", "llm"]
        assert payloads[0]["input"] == "hello"


# =============================================================================
# CONTROL NAME TESTS
# =============================================================================

class TestPolicyHandling:
    """Tests for policy-based control evaluation."""

    @pytest.mark.asyncio
    async def test_control_triggers_raise_exception(self, mock_agent, mock_unsafe_response):
        """Test that matching control triggers raise ControlViolationError."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=mock_unsafe_response):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            with pytest.raises(ControlViolationError) as exc_info:
                await chat("Test")

            assert exc_info.value.control_name == "test-control"

    @pytest.mark.asyncio
    async def test_steer_action_raises_exception(self, mock_agent, mock_steer_response):
        """Test that steer action raises ControlSteerError with steering context."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=mock_steer_response):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            with pytest.raises(ControlSteerError) as exc_info:
                await chat("Test offensive message")

            # Verify exception has all expected fields
            assert exc_info.value.control_name == "steer-control"
            assert exc_info.value.message == "Inappropriate language detected"
            assert exc_info.value.steering_context == "Please rephrase your question using respectful language"
            assert "steer-control" in str(exc_info.value)
            assert "Please rephrase" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_policy_evaluates_all_controls(self, mock_agent, mock_safe_response):
        """Test that policy evaluates all controls."""
        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", return_value=mock_safe_response) as mock_eval:

            @control()  # Apply agent's assigned policy
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            await chat("Hello!")

            # Verify evaluate was called
            assert mock_eval.called


# =============================================================================
# PRE AND POST EXECUTION TESTS
# =============================================================================

class TestPrePostExecution:
    """Tests for pre and post execution checks."""

    @pytest.mark.asyncio
    async def test_uses_external_provider_trace_context(self, mock_agent, mock_safe_response):
        """Test that an external provider supplies both trace and span IDs."""
        # Given: an external telemetry provider that owns the active trace/span IDs
        provided_trace_id = "6c4e3f7e-4a9a-4e7e-8c1f-3a9a3a9a3a9d"
        provided_span_id = "8d30272e-23f7-4a4c-80d8-2decb2f3f9f8"
        captured_contexts = []

        async def mock_evaluate(
            agent_name,
            step,
            stage,
            server_url,
            trace_id=None,
            span_id=None,
            controls=None,
            event_agent_name=None,
        ):
            captured_contexts.append((trace_id, span_id))
            return mock_safe_response

        set_trace_context_provider(
            lambda: {"trace_id": provided_trace_id, "span_id": provided_span_id}
        )
        try:
            with (
                patch(
                    "agent_control.control_decorators._get_current_agent",
                    return_value=mock_agent,
                ),
                patch("agent_control.control_decorators._evaluate", side_effect=mock_evaluate),
            ):

                @control()
                async def chat(message: str) -> str:
                    return f"Response to: {message}"

                # When: a protected function runs pre and post checks
                await chat("Hello!")
        finally:
            clear_trace_context_provider()

        # Then: Agent Control preserves the provider's concrete target span ID
        assert captured_contexts == [
            (provided_trace_id, provided_span_id),
            (provided_trace_id, provided_span_id),
        ]

    @pytest.mark.asyncio
    async def test_calls_pre_and_post(self, mock_agent, mock_safe_response):
        """Test that both pre and post checks are called."""
        call_stages = []

        async def mock_evaluate(
            agent_name,
            step,
            stage,
            server_url,
            trace_id=None,
            span_id=None,
            controls=None,
            event_agent_name=None,
        ):
            call_stages.append(stage)
            return mock_safe_response

        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", side_effect=mock_evaluate):

            @control()
            async def chat(message: str) -> str:
                return f"Response to: {message}"

            await chat("Hello!")

            assert "pre" in call_stages
            assert "post" in call_stages

    @pytest.mark.asyncio
    async def test_pre_block_prevents_execution(self, mock_agent, mock_safe_response, mock_unsafe_response):
        """Test that pre-check block prevents function execution."""
        function_executed = False

        async def mock_evaluate(
            agent_name,
            step,
            stage,
            server_url,
            trace_id=None,
            span_id=None,
            controls=None,
            event_agent_name=None,
        ):
            if stage == "pre":
                return mock_unsafe_response
            return mock_safe_response

        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", side_effect=mock_evaluate):

            @control()
            async def chat(message: str) -> str:
                nonlocal function_executed
                function_executed = True
                return f"Response to: {message}"

            with pytest.raises(ControlViolationError):
                await chat("Blocked message")

            assert not function_executed

    @pytest.mark.asyncio
    async def test_post_check_receives_output(self, mock_agent, mock_safe_response):
        """Test that post-check receives the function output."""
        captured_step = {}

        async def mock_evaluate(
            agent_name,
            step,
            stage,
            server_url,
            trace_id=None,
            span_id=None,
            controls=None,
            event_agent_name=None,
        ):
            if stage == "post":
                captured_step.update(step)
            return mock_safe_response

        with patch("agent_control.control_decorators._get_current_agent", return_value=mock_agent), \
             patch("agent_control.control_decorators._evaluate", side_effect=mock_evaluate):

            @control()
            async def chat(message: str) -> str:
                return "Generated response"

            await chat("Hello!")

            assert "output" in captured_step
            assert "Generated response" in captured_step["output"]


# =============================================================================
# INPUT EXTRACTION TESTS
# =============================================================================

class TestInputExtraction:
    """Tests for automatic input extraction from function arguments."""

    @pytest.mark.asyncio
    async def test_extracts_input_param(self, mock_agent, mock_safe_response):
        """Test extraction of 'input' parameter."""
        captured_step = {}

        async def mock_evaluate(
            agent_name,
            step,
