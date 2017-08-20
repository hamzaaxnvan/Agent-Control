"""Unit tests for Strands hook integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from agent_control_models import EvaluationResult


@pytest.fixture
def mock_strands_modules():
    """Mock the strands modules to avoid import errors."""
    with patch.dict(
        "sys.modules",
        {
            "strands": MagicMock(),
            "strands.hooks": MagicMock(),
            "strands.plugins": MagicMock(),
        },
    ):
        yield


@pytest.fixture
def mock_event_classes():
    """Create mock event classes."""
    BeforeInvocationEvent = type("BeforeInvocationEvent", (), {})  # noqa: N806
    BeforeModelCallEvent = type("BeforeModelCallEvent", (), {})  # noqa: N806
    AfterModelCallEvent = type("AfterModelCallEvent", (), {})  # noqa: N806
    BeforeToolCallEvent = type("BeforeToolCallEvent", (), {})  # noqa: N806
    AfterToolCallEvent = type("AfterToolCallEvent", (), {})  # noqa: N806
    BeforeNodeCallEvent = type("BeforeNodeCallEvent", (), {})  # noqa: N806
    AfterNodeCallEvent = type("AfterNodeCallEvent", (), {})  # noqa: N806
    Plugin = type("Plugin", (), {"__init__": lambda self: None})  # noqa: N806

    return {
        "BeforeInvocationEvent": BeforeInvocationEvent,
        "BeforeModelCallEvent": BeforeModelCallEvent,
        "AfterModelCallEvent": AfterModelCallEvent,
        "BeforeToolCallEvent": BeforeToolCallEvent,
        "AfterToolCallEvent": AfterToolCallEvent,
        "BeforeNodeCallEvent": BeforeNodeCallEvent,
        "AfterNodeCallEvent": AfterNodeCallEvent,
        "Plugin": Plugin,
    }


@pytest.fixture
def agent_control_hook(mock_strands_modules, mock_event_classes):
    """Create an AgentControlPlugin instance with mocked dependencies."""
    import importlib
    import sys
    import agent_control.integrations.strands.plugin as plugin_module

    hooks_mod = sys.modules["strands.hooks"]
    for name, cls in mock_event_classes.items():
        setattr(hooks_mod, name, cls)

    plugins_mod = sys.modules["strands.plugins"]
    plugins_mod.Plugin = mock_event_classes["Plugin"]

    importlib.reload(plugin_module)

    return plugin_module.AgentControlPlugin(agent_name="test-agent")


def test_action_error_with_deny_match():
    """Test _action_error returns deny error for deny action."""
    from agent_control.integrations.strands.plugin import _action_error

    # Create a mock match with deny action
    mock_match = MagicMock()
    mock_match.action = "deny"
    mock_match.control_name = "test_control"
    mock_match.result.message = "Access denied"

    # Create a mock result
    result = MagicMock(spec=EvaluationResult)
    result.matches = [mock_match]
    result.reason = None

    action_type, error = _action_error(result)

    assert action_type == "deny"
    assert "Control violation [test_control]" in str(error)
    assert "Access denied" in str(error)


def test_action_error_with_steer_match():
    """Test _action_error returns steer error for steer action."""
    from agent_control.integrations.strands.plugin import _action_error

    # Create a mock match with steer action
    mock_match = MagicMock()
    mock_match.action = "steer"
    mock_match.control_name = "test_control"
    mock_match.result.message = "Steering required"
    mock_match.steering_context.message = "Context message"

    # Create a mock result
    result = MagicMock(spec=EvaluationResult)
    result.matches = [mock_match]
    result.reason = None

    action_type, error = _action_error(result)

    assert action_type == "steer"
    assert "Steering required [test_control]" in str(error)


def test_action_error_with_no_blocking_match():
    """Test _action_error returns None when no blocking matches."""
    from agent_control.integrations.strands.plugin import _action_error

    # Create a mock match with observe action
    mock_match = MagicMock()
    mock_match.action = "observe"

    # Create a mock result
    result = MagicMock(spec=EvaluationResult)
    result.matches = [mock_match]

    assert _action_error(result) is None


def test_action_error_with_empty_matches():
    """Test _action_error returns None with empty matches."""
    from agent_control.integrations.strands.plugin import _action_error

    result = MagicMock(spec=EvaluationResult)
    result.matches = []

    assert _action_error(result) is None


def test_action_error_with_none_matches():
    """Test _action_error returns None with None matches."""
    from agent_control.integrations.strands.plugin import _action_error

    result = MagicMock(spec=EvaluationResult)
    result.matches = None

    assert _action_error(result) is None


def test_action_error_deny_takes_precedence():
    """Test deny takes precedence over steer regardless of order."""
    from agent_control.integrations.strands.plugin import _action_error
    from agent_control import ControlViolationError

    deny = MagicMock()
    deny.action = "deny"
    deny.control_name = "deny-control"
    deny.control_id = 1
    deny.result.message = "Denied"

    steer = MagicMock()
    steer.action = "steer"
    steer.control_name = "steer-control"
    steer.control_id = 2
    steer.result.message = "Steer"

    result = MagicMock(spec=EvaluationResult)
    # Steer appears first to ensure deny-first behavior
    result.matches = [steer, deny]
    result.reason = None

    action, err = _action_error(result)

    assert action == "deny"
    assert isinstance(err, ControlViolationError)
    assert err.control_name == "deny-control"


@pytest.mark.asyncio
async def test_evaluate_and_enforce_safe_result(agent_control_hook):
    """Test _evaluate_and_enforce with safe result."""
    with patch("agent_control.integrations.strands.plugin.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        # Mock a safe result
        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.is_safe = True
        mock_result.matches = []
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        # Should not raise
        await agent_control_hook._evaluate_and_enforce(
            step_name="test_step",
            input="test input",
            step_type="llm",
            stage="pre"
        )


@pytest.mark.asyncio
async def test_evaluate_and_enforce_with_errors(agent_control_hook):
    """Test _evaluate_and_enforce fails closed on evaluation errors."""
    with patch("agent_control.integrations.strands.plugin.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        mock_error = MagicMock()
        mock_error.control_name = "error-control"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.errors = [mock_error]
        mock_result.is_safe = True
        mock_result.matches = []
        mock_evaluate.return_value = mock_result

        with pytest.raises(RuntimeError):
            await agent_control_hook._evaluate_and_enforce(
                step_name="test_step",
                input="test input",
                step_type="llm",
                stage="pre"
            )


@pytest.mark.asyncio
async def test_evaluate_and_enforce_with_deny(agent_control_hook):
    """Test _evaluate_and_enforce raises error on deny action."""
    with patch("agent_control.integrations.strands.plugin.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        from agent_control import ControlViolationError

        # Mock a deny result
        mock_match = MagicMock()
        mock_match.action = "deny"
        mock_match.control_name = "test_control"
        mock_match.result.message = "Denied"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.is_safe = True
        mock_result.matches = [mock_match]
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        with pytest.raises(ControlViolationError):
            await agent_control_hook._evaluate_and_enforce(
                step_name="test_step",
                input="test input",
                step_type="llm",
                stage="pre"
            )


@pytest.mark.asyncio
async def test_evaluate_and_enforce_with_steer(agent_control_hook):
    """Test _evaluate_and_enforce raises error on steer action."""
    with patch("agent_control.integrations.strands.plugin.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        from agent_control import ControlSteerError

        # Mock a steer result
        mock_match = MagicMock()
        mock_match.action = "steer"
        mock_match.control_name = "test_control"
        mock_match.control_id = 42
        mock_match.result.message = "Steer required"
        mock_match.result.metadata = {"risk": "high"}
        mock_match.steering_context.message = "Context"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.is_safe = True
        mock_result.matches = [mock_match]
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        with pytest.raises(ControlSteerError) as exc_info:
            await agent_control_hook._evaluate_and_enforce(
                step_name="test_step",
                input="test input",
                step_type="llm",
                stage="pre"
            )

        err = exc_info.value
        assert err.control_name == "test_control"
        assert err.control_id == 42
        assert err.metadata == {"risk": "high"}
        assert "Context" in err.steering_context


@pytest.mark.asyncio
async def test_evaluate_and_enforce_unsafe_result(agent_control_hook):
    """Test _evaluate_and_enforce raises error on unsafe result."""
    with patch("agent_control.integrations.strands.plugin.agent_control.evaluate_controls") as mock_evaluate:  # noqa: E501
        from agent_control import ControlViolationError

        # Mock an unsafe result
        mock_match = MagicMock()
        mock_match.action = "observe"
        mock_match.control_name = "test_control"
        mock_match.result.message = "Unsafe"

        mock_result = MagicMock(spec=EvaluationResult)
        mock_result.is_safe = False
        mock_result.matches = [mock_match]
        mock_result.reason = "Test reason"
        mock_result.errors = []
        mock_evaluate.return_value = mock_result

        with pytest.raises(ControlViolationError) as exc_info:
            await agent_control_hook._evaluate_and_enforce(
                step_name="test_step",
                input="test input",
                step_type="llm",
                stage="pre"
            )

        assert "test_control" in str(exc_info.value)


def test_extract_content_text_with_string(agent_control_hook):
    """Test _extract_content_text with string input."""
    result = agent_control_hook._extract_content_text("test string")
    assert result == "test string"


def test_extract_content_text_with_dict_text(agent_control_hook):
    """Test _extract_content_text with dict containing text."""
    result = agent_control_hook._extract_content_text({"text": "test text"})
    assert result == "test text"


def test_extract_content_text_with_dict_json(agent_control_hook):
    """Test _extract_content_text with dict containing json."""
    result = agent_control_hook._extract_content_text({"json": {"key": "value"}})
    assert "key" in result
