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

    async def _evaluate_and_enforce(
        self,
        step_name: str,
        input: Any | None = None,
        output: Any | None = None,
        context: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        step_type: Literal["tool", "llm"] = "llm",
        stage: Literal["pre", "post"] = "pre",
        use_runtime_error: bool = False,
    ) -> None:
        result = await agent_control.evaluate_controls(
            step_name=step_name,
            input=input,
            output=output,
            context=context,
            tools=tools,
            step_type=step_type,
            stage=stage,
            agent_name=self.agent_name,
        )

        if result.errors:
            error_names = ", ".join(
                e.control_name for e in result.errors if getattr(e, "control_name", None)
            )
            self._raise_error(
                RuntimeError(
                    "Control evaluation failed; execution blocked for safety. "
                    f"Errors: {error_names or 'unknown'}"
                ),
                use_runtime_error,
            )

        action = _action_error(result)
        if action:
            _, err = action
            control_name = getattr(err, "control_name", "unknown")
            self._invoke_callback(control_name, stage, result)
            if isinstance(err, ControlSteerError):
                logger.debug(
                    "agent=<%s>, step=<%s>, stage=<%s> | steering required",
                    self.agent_name,
                    step_name,
                    stage,
                )
            self._raise_error(err, use_runtime_error)

        if not result.is_safe:
            control_name = "unknown"
            reason = result.reason

            if result.matches:
                first_match = result.matches[0]
                control_name = first_match.control_name
                if not reason:
                    match_result = getattr(first_match, "result", None)
                    msg = getattr(match_result, "message", None) if match_result else None
                    reason = msg or f"Control '{control_name}' triggered"

            logger.debug(
                "agent=<%s>, control=<%s> | control violation",
                self.agent_name,
                control_name,
            )
            self._invoke_callback(control_name, stage, result)
            self._raise_error(
                ControlViolationError(
                    control_name=control_name,
                    message=reason or "Control violation",
                    metadata=(
                        getattr(first_match.result, "metadata", None)
                        if result.matches
                        else None
                    ),
                ),
                use_runtime_error,
            )

    def init_agent(self, agent: Any) -> None:
        self._tool_registry = getattr(agent, "tool_registry", None)
        event_map = {
            BeforeInvocationEvent: self.check_before_invocation,
            BeforeModelCallEvent: self.check_before_model,
            AfterModelCallEvent: self.check_after_model,
            BeforeToolCallEvent: self.check_before_tool,
            AfterToolCallEvent: self.check_after_tool,
            BeforeNodeCallEvent: self.check_before_node,
            AfterNodeCallEvent: self.check_after_node,
        }

        events_to_register = (
            self.event_control_list if self.event_control_list else event_map.keys()
        )

        if self.enable_logging:
            logger.debug(
                "agent=<%s>, events=<%s> | registering hooks",
                self.agent_name,
                ",".join([e.__name__ for e in events_to_register if e in event_map]),
            )

        for event_type in events_to_register:
            if event_type in event_map:
                agent.add_hook(event_map[event_type], event_type)

    async def check_before_invocation(self, event: BeforeInvocationEvent) -> None:
        input_text, _ = self._extract_messages(event)
        await self._evaluate_and_enforce(
            step_name="check_before_invocation",
