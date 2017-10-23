"""Unit tests for Strands steering integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from agent_control_models import EvaluationResult


@pytest.fixture
def mock_strands_steering_modules():
    """Mock the strands steering modules to avoid import errors."""
    Guide = type("Guide", (), {"__init__": lambda self, reason: setattr(self, "reason", reason)})  # noqa: N806
    Proceed = type("Proceed", (), {"__init__": lambda self, reason: setattr(self, "reason", reason)})  # noqa: N806, E501
    SteeringHandler = type("SteeringHandler", (), {"__init__": lambda self: None})  # noqa: N806

    with patch.dict(
        "sys.modules",
        {
            "strands": MagicMock(),
            "strands.experimental": MagicMock(),
            "strands.experimental.steering": MagicMock(
                Guide=Guide,
                Proceed=Proceed,
                SteeringHandler=SteeringHandler,
            ),
        },
    ):
        # Also patch the imports in the module
        with patch("agent_control.integrations.strands.steering.Guide", Guide):
            with patch("agent_control.integrations.strands.steering.Proceed", Proceed):
                with patch("agent_control.integrations.strands.steering.SteeringHandler", SteeringHandler):  # noqa: E501
                    yield {
                        "Guide": Guide,
                        "Proceed": Proceed,
                        "SteeringHandler": SteeringHandler,
                    }


@pytest.fixture
def steering_handler(mock_strands_steering_modules):
    """Create an AgentControlSteeringHandler instance."""
    from agent_control.integrations.strands.steering import AgentControlSteeringHandler

    return AgentControlSteeringHandler(agent_name="test-agent", enable_logging=False)


def test_steering_handler_initialization(mock_strands_steering_modules):
    """Test AgentControlSteeringHandler initialization."""
    from agent_control.integrations.strands.steering import AgentControlSteeringHandler

    handler = AgentControlSteeringHandler(agent_name="test-agent", enable_logging=True)

    assert handler.agent_name == "test-agent"
    assert handler.enable_logging is True
    assert handler.steers_applied == 0
    assert handler.last_steer_info is None


@pytest.mark.asyncio
async def test_steer_after_model_with_steer_match(steering_handler, mock_strands_steering_modules):
    """Test steer_after_model returns Guide when steer match found."""
    with patch("agent_control.integrations.strands.steering.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        # Mock a steer match
        mock_match = MagicMock()
        mock_match.action = "steer"
        mock_match.control_name = "test_control"
        mock_match.result.message = "Steering required"
        mock_match.steering_context.message = "Steering context"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.matches = [mock_match]
        mock_result.reason = None
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        # Create mock message
        message = {"content": [{"text": "test output"}]}

        result = await steering_handler.steer_after_model(
            agent=MagicMock(),
            message=message,
            stop_reason="end_turn"
        )

        # Check that Guide was returned
        assert result.__class__.__name__ == "Guide"
        assert result.reason == "Steering context"
        assert steering_handler.steers_applied == 1
        assert steering_handler.last_steer_info is not None
        assert steering_handler.last_steer_info["control_name"] == "test_control"


@pytest.mark.asyncio
async def test_steer_after_model_with_deny_match(steering_handler, mock_strands_steering_modules):
    """Test steer_after_model raises ControlViolationError on deny."""
    with patch("agent_control.integrations.strands.steering.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        from agent_control import ControlViolationError

        # Mock a deny match
        mock_match = MagicMock()
        mock_match.action = "deny"
        mock_match.control_name = "test_control"
        mock_match.result.message = "Access denied"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.matches = [mock_match]
        mock_result.reason = None
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        # Create mock message
        message = {"content": [{"text": "test output"}]}

        with pytest.raises(ControlViolationError) as exc_info:
            await steering_handler.steer_after_model(
                agent=MagicMock(),
                message=message,
                stop_reason="end_turn"
            )

        assert "Control violation [test_control]" in str(exc_info.value)
        assert "Access denied" in str(exc_info.value)


@pytest.mark.asyncio
async def test_steer_after_model_deny_takes_precedence(steering_handler, mock_strands_steering_modules):
    """Test deny is enforced even if steer is also present."""
    with patch("agent_control.integrations.strands.steering.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        from agent_control import ControlViolationError

        deny_match = MagicMock()
        deny_match.action = "deny"
        deny_match.control_name = "deny_control"
        deny_match.control_id = 1
        deny_match.result.message = "Access denied"

        steer_match = MagicMock()
        steer_match.action = "steer"
        steer_match.control_name = "steer_control"
        steer_match.control_id = 2
        steer_match.result.message = "Steer required"
        steer_match.steering_context.message = "Context"

        mock_result = MagicMock(spec=EvaluationResult)
        # Steer first to ensure deny-first logic
        mock_result.matches = [steer_match, deny_match]
        mock_result.reason = None
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        message = {"content": [{"text": "test output"}]}

        with pytest.raises(ControlViolationError) as exc_info:
            await steering_handler.steer_after_model(
                agent=MagicMock(),
                message=message,
                stop_reason="end_turn"
            )

        assert "deny_control" in str(exc_info.value)


@pytest.mark.asyncio
async def test_steer_after_model_with_result_errors(steering_handler, mock_strands_steering_modules):
    """Test steer_after_model fails closed on evaluation errors."""
    with patch("agent_control.integrations.strands.steering.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        mock_error = MagicMock()
        mock_error.control_name = "error-control"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.errors = [mock_error]
        mock_result.matches = []
        mock_evaluate.return_value = mock_result

        message = {"content": [{"text": "test output"}]}

        with pytest.raises(RuntimeError):
            await steering_handler.steer_after_model(
                agent=MagicMock(),
                message=message,
                stop_reason="end_turn"
            )


@pytest.mark.asyncio
async def test_steer_after_model_no_matches(steering_handler, mock_strands_steering_modules):
    """Test steer_after_model returns Proceed when no matches."""
    with patch("agent_control.integrations.strands.steering.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        # Mock no matches
        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.matches = []
