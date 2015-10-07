"""Unit tests for shared framework integration helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_control_models import EvaluationResult

from agent_control import ControlSteerError, ControlViolationError
from agent_control.integrations._core import _action_error, _evaluate_and_enforce


def _match(
    *,
    action: str,
    control_name: str = "test-control",
    control_id: int = 1,
    message: str = "blocked",
    steering_context: str | None = None,
) -> SimpleNamespace:
    ctx = (
        SimpleNamespace(message=steering_context)
        if steering_context is not None
        else None
    )
    return SimpleNamespace(
        action=action,
        control_name=control_name,
        control_id=control_id,
        result=SimpleNamespace(message=message, metadata={"source": "test"}),
        steering_context=ctx,
    )


def test_action_error_returns_deny():
    result = MagicMock(spec=EvaluationResult)
    result.matches = [_match(action="deny", message="Denied")]
    result.reason = None

    action, err = _action_error(result) or ("", Exception())

    assert action == "deny"
    assert isinstance(err, ControlViolationError)
    assert err.control_name == "test-control"


def test_action_error_returns_steer():
    result = MagicMock(spec=EvaluationResult)
    result.matches = [_match(action="steer", message="Steer", steering_context="Rewrite it")]
    result.reason = None

    action, err = _action_error(result) or ("", Exception())

    assert action == "steer"
    assert isinstance(err, ControlSteerError)
    assert err.steering_context == "Rewrite it"


