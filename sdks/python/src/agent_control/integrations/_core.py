"""Shared enforcement helpers for framework integrations."""

from __future__ import annotations

from typing import Any, Literal

from agent_control_models import EvaluationResult, JSONValue

import agent_control
from agent_control import ControlSteerError, ControlViolationError


def _action_error(result: EvaluationResult) -> tuple[str, Exception] | None:
    """Return the first blocking action from an evaluation result."""

    matches = result.matches or []
    deny_match = next((m for m in matches if m.action == "deny"), None)
    if deny_match:
        msg = getattr(getattr(deny_match, "result", None), "message", None) or result.reason
        msg = msg or f"Control '{deny_match.control_name}' triggered"
        deny_err = ControlViolationError(
            control_id=deny_match.control_id,
            control_name=deny_match.control_name,
            message=msg,
            metadata=getattr(deny_match.result, "metadata", None),
        )
        return "deny", deny_err

    steer_match = next((m for m in matches if m.action == "steer"), None)
    if not steer_match:
        return None

    msg = getattr(getattr(steer_match, "result", None), "message", None) or result.reason
    msg = msg or f"Control '{steer_match.control_name}' triggered"
    ctx = getattr(steer_match, "steering_context", None)
    ctx_msg = getattr(ctx, "message", None) if ctx else None
    steer_err = ControlSteerError(
        control_id=steer_match.control_id,
        control_name=steer_match.control_name,
        message=f"Steering required [{steer_match.control_name}]: {msg}",
        metadata=getattr(steer_match.result, "metadata", None),
        steering_context=ctx_msg or msg,
    )
    return "steer", steer_err


async def _evaluate_and_enforce(
    agent_name: str,
    step_name: str,
    *,
    input: Any | None = None,
    output: Any | None = None,
    context: dict[str, Any] | None = None,
