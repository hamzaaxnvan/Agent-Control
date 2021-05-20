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
