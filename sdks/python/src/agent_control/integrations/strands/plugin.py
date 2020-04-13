"""Agent Control plugin integration for Strands."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from agent_control_models import EvaluationResult

import agent_control
from agent_control import ControlSteerError, ControlViolationError
from agent_control.integrations._tools import normalize_strands_tool_specs

try:
    from strands.hooks import (  # type: ignore[import-not-found]
        AfterModelCallEvent,
        AfterNodeCallEvent,
        AfterToolCallEvent,
        BeforeInvocationEvent,
        BeforeModelCallEvent,
        BeforeNodeCallEvent,
        BeforeToolCallEvent,
    )
    from strands.plugins import Plugin  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - optional dependency
    raise RuntimeError(
        "Strands integration requires strands-agents. "
        "Install with: agent-control-sdk[strands-agents]."
    ) from exc

logger = logging.getLogger(__name__)


def _action_error(result: EvaluationResult) -> tuple[str, Exception] | None:
    """Return the first blocking action as an exception."""

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


class AgentControlPlugin(Plugin):
    """Plugin that integrates Agent Control with Strands lifecycle events.

    The Agent Control server is required for control distribution and policy assignment.
    Controls may specify execution="sdk" or execution="server".
    Strands lifecycle events handled by this adapter are model and tool events,
    so its internal step-type annotations intentionally remain limited to
    ``llm`` and ``tool``. Custom types remain available through the core SDK APIs.
    """

    name = "agent-control-plugin"

    def __init__(
        self,
        agent_name: str,
        event_control_list: list[type] | None = None,
        on_violation_callback: Callable[[dict[str, Any], EvaluationResult], None] | None = None,
        enable_logging: bool = True,
    ) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.event_control_list = event_control_list
        self.on_violation_callback = on_violation_callback
        self.enable_logging = enable_logging
        self._tool_registry: Any | None = None

    def _invoke_callback(self, control_name: str, stage: str, result: EvaluationResult) -> None:
        if self.on_violation_callback:
            self.on_violation_callback(
                {
                    "agent": self.agent_name,
                    "control_name": control_name,
                    "stage": stage,
                },
                result,
            )

    def _raise_error(self, error: Exception, use_runtime_error: bool) -> None:
        if use_runtime_error:
            raise RuntimeError(str(error))
        raise error

