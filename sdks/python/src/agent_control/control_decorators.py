"""
Control decorator for server-side protection of agent functions.

This module provides a decorator that applies server-defined controls to agent functions.
Controls can be associated via policies and direct agent-control links.

Architecture:
    SERVER defines: Policies -> Controls (stage, condition tree, action)
    SDK decorator: just marks WHERE controls are evaluated

Usage:
    import agent_control

    agent_control.init(
        agent_name="my-agent-identity",
    )

    # Apply controls associated with the agent
    @agent_control.control()
    async def chat(message: str) -> str:
        return await assistant.respond(message)

    # Server-side controls define:
    # - stage: "pre" or "post"
    # - selector.path: "input" or "output"
    # - evaluator: regex, list, Luna evaluator, LLM evaluator, etc.
    # - action: deny, steer, or observe
"""

import asyncio
import functools
import inspect
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agent_control_models import JSONObject, Step, normalize_action
from agent_control_telemetry import get_trace_context_from_provider

from agent_control import AgentControlClient
from agent_control._state import state
from agent_control.evaluation import (
    _post_evaluation_request,
    _resolve_session_target,
    check_evaluation_with_local,
)
from agent_control.observability import (
    get_logger,
    log_control_evaluation,
    log_span_end,
    log_span_start,
)
from agent_control.settings import get_settings
from agent_control.tracing import _generate_span_id, get_current_trace_id, get_trace_and_span_ids
from agent_control.validation import ensure_step_type

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])
type ToolsProvider = Callable[
    [tuple[Any, ...], Mapping[str, Any]], Sequence[JSONObject] | None
]
type ToolsConfiguration = Sequence[JSONObject] | ToolsProvider | None


def _resolve_control_trace_context() -> tuple[str, str]:
    """Resolve trace/span IDs for a decorated control site.

    External providers, such as the Galileo bridge, are authoritative because
    they may reserve the concrete span ID that the eventual LLM/tool call will
    use. Without a provider, keep the existing behavior: share an active trace
    but create a fresh function span for this decorated call.
    """
    provider_context = get_trace_context_from_provider()
    if provider_context is not None:
        return provider_context["trace_id"], provider_context["span_id"]

    existing_trace_id = get_current_trace_id()
    if existing_trace_id:
        return existing_trace_id, _generate_span_id()

    return get_trace_and_span_ids()


@dataclass
class ControlContext:
    """
    Holds state during control execution.

    This class encapsulates all the shared logic between async and sync
    control wrappers, including stats tracking, result processing, and logging.
    """

    agent_name: str
    server_url: str
    func: Callable
    args: tuple
    kwargs: dict
    trace_id: str
    span_id: str
    start_time: float
    step_name: str | None = None
    step_type: str | None = None
    tools: ToolsConfiguration = None

    # Stats (mutually exclusive: errors vs matches vs non_matches)
    total_executions: int = 0
    total_matches: int = 0
    total_non_matches: int = 0
    total_errors: int = 0
    actions: dict[str, int] = field(default_factory=dict)

    def log_start(self) -> None:
        """Log span start."""
        log_span_start(self.trace_id, self.span_id, self.func.__name__, self.agent_name)

    def log_end(self) -> None:
        """Log span end with accumulated stats."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        log_span_end(
            self.trace_id,
            self.span_id,
            self.func.__name__,
            duration_ms,
            executions=self.total_executions,
            matches=self.total_matches,
            non_matches=self.total_non_matches,
            errors=self.total_errors,
            actions=self.actions if self.actions else None,
        )

    def pre_payload(self) -> dict[str, Any]:
        """Build payload for pre-execution check (supports tool call detection)."""
        return _create_evaluation_payload(
            self.func,
            self.args,
            self.kwargs,
            output=None,
            step_name=self.step_name,
            explicit_step_type=self.step_type,
            tools=self.tools,
        )

    def post_payload(self, output: Any) -> dict[str, Any]:
        """Build payload for post-execution check (supports tool call detection)."""
        return _create_evaluation_payload(
            self.func,
            self.args,
            self.kwargs,
            output=output,
            step_name=self.step_name,
            explicit_step_type=self.step_type,
            tools=self.tools,
        )

    def process_result(self, result: dict[str, Any], check_stage: str) -> None:
        """
        Process evaluation result: log, handle actions, update stats.

        Args:
            result: Server evaluation response
            check_stage: "pre" or "post"

        Raises:
            ControlViolationError: If any control triggers with "deny" action
            ControlSteerError: If any control triggers with "steer" action
        """
        # Log each control evaluation
        _log_control_evaluations(result, self.trace_id, self.span_id, check_stage)

        # Handle deny/steer/observe actions (may raise ControlViolationError, ControlSteerError)
        _handle_evaluation_result(result)

        # Update stats in place
        self._update_stats(result)

    def _update_stats(self, result: dict[str, Any]) -> None:
        """
        Update stats in place from evaluation result.

        The server returns three mutually exclusive lists:
        - matches: controls where condition matched
        - non_matches: controls that were evaluated but didn't match
        - errors: controls that failed during evaluation
        """
        # Process matches (controls that matched)
        for match in result.get("matches") or []:
            self.total_executions += 1
            self.total_matches += 1
            action = normalize_action(str(match.get("action", "observe")))
            self.actions[action] = self.actions.get(action, 0) + 1

        # Process non-matches (controls evaluated but didn't match)
        for _ in result.get("non_matches") or []:
            self.total_executions += 1
            self.total_non_matches += 1

        # Process errors (controls that failed evaluation)
        for _ in result.get("errors") or []:
            self.total_executions += 1
            self.total_errors += 1


class ControlViolationError(Exception):
    """Raised when a control is triggered with 'deny' action."""

    def __init__(
        self,
        control_id: int | str | None = None,
        control_name: str | None = None,
        message: str = "Control violation",
        metadata: dict[str, Any] | None = None
    ):
        self.control_id = control_id
        self.control_name = control_name or (str(control_id) if control_id else "unknown")
        self.message = message
        self.metadata = metadata or {}
        super().__init__(f"Control violation [{self.control_name}]: {message}")


class ControlSteerError(Exception):
    """Raised when a control is triggered with 'steer' action.

    This error indicates the agent should modify its approach based on
    the provided steering context and potentially retry the operation.

    Unlike ControlViolationError (deny), this is not a hard block but
    a corrective signal that allows the application to adjust and retry.
    """

    def __init__(
        self,
        control_id: int | str | None = None,
        control_name: str | None = None,
        message: str = "Control steering required",
        metadata: dict[str, Any] | None = None,
        steering_context: str | None = None,
        input_data: Any | None = None,
        output_data: Any | None = None
    ):
        self.control_id = control_id
        self.control_name = control_name or (str(control_id) if control_id else "unknown")
        self.message = message
        self.metadata = metadata or {}
        self.steering_context = steering_context or self.metadata.get(
            "steering_context", "No steering context provided"
        )
        self.input_data = input_data
        self.output_data = output_data
        super().__init__(
            f"Control steering [{self.control_name}]: {message}\n"
            f"Steering context: {self.steering_context}"
        )


class _InvalidToolsConfigurationError(ValueError):
    """Raised when decorator tools are configured for a non-LLM step."""


def _get_current_agent() -> Any | None:
    """Get the current agent from agent_control module."""
    try:
        import agent_control
        return agent_control.current_agent()
    except Exception:
        return None


def _get_server_url() -> str:
    """Get the server URL from settings."""
    return get_settings().url


async def _evaluate(
    agent_name: str,
    step: dict[str, Any],
    stage: str,
    server_url: str,
    trace_id: str | None = None,
    span_id: str | None = None,
    controls: list[dict[str, Any]] | None = None,
    event_agent_name: str | None = None,
) -> dict[str, Any]:
    """Call evaluation with support for local (SDK) and server execution.

    If controls are provided, uses check_evaluation_with_local() which:
    - Evaluates execution="sdk" controls locally in the SDK
    - Sends execution="server" controls to the server

    If no controls provided, falls back to server-only evaluation.
    """
    # Build headers with trace/span IDs for distributed tracing
    headers = {}
    if trace_id:
        headers["X-Trace-Id"] = trace_id
    if span_id:
        headers["X-Span-Id"] = span_id

    target_type, target_id = _resolve_session_target(None, None)

    async with AgentControlClient(
        base_url=server_url,
        api_key=state.api_key,
        api_key_header=state.api_key_header,
        runtime_token_header=state.runtime_token_header,
        runtime_token_cache=state.runtime_token_cache,
    ) as client:
        # If we have controls, use local evaluation which handles both SDK and server controls
        if controls is not None:
            try:
                # Build Step object for evaluation
                step_obj = Step(**step)

                result = await check_evaluation_with_local(
                    client=client,
                    agent_name=agent_name,
                    step=step_obj,
                    stage=stage,  # type: ignore
                    controls=controls,
                    target_type=target_type,
                    target_id=target_id,
                    trace_id=trace_id,
                    span_id=span_id,
                    event_agent_name=event_agent_name,
                )

                # Convert result to dict format expected by process_result
                # Build a lookup map for control definitions by ID
                control_defs_by_id = {
                    c.get("id"): c.get("control", {})
                    for c in controls if isinstance(c, dict)
                }

                return {
                    "is_safe": result.is_safe,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "matches": [
                        {
                            "control_id": m.control_id,
                            "control_name": m.control_name,
                            "action": m.action,
                            "control": control_defs_by_id.get(m.control_id, {}),
                            "result": {
                                "matched": m.result.matched,
                                "confidence": m.result.confidence,
                                "message": m.result.message,
                                "error": m.result.error,
                                "metadata": m.result.metadata,
                            },
                            "control_execution_id": m.control_execution_id,
                            "execution_duration_ms": m.execution_duration_ms,
                            "steering_context": (
                                {"message": m.steering_context.message}
                                if m.steering_context else None
                            ),
                        }
                        for m in (result.matches or [])
                    ] if result.matches else None,
                    "errors": [
                        {
                            "control_id": e.control_id,
                            "control_name": e.control_name,
                            "action": e.action,
                            "control": control_defs_by_id.get(e.control_id, {}),
                            "result": {
                                "matched": e.result.matched,
                                "confidence": e.result.confidence,
                                "message": e.result.message,
                                "error": e.result.error,
                                "metadata": e.result.metadata,
                            },
                            "control_execution_id": e.control_execution_id,
                            "execution_duration_ms": e.execution_duration_ms,
                            "steering_context": (
                                {"message": e.steering_context.message}
                                if e.steering_context else None
                            ),
                        }
                        for e in (result.errors or [])
                    ] if result.errors else None,
                    "non_matches": [
                        {
                            "control_id": nm.control_id,
                            "control_name": nm.control_name,
                            "action": nm.action,
                            "control": control_defs_by_id.get(nm.control_id, {}),
                            "result": {
                                "matched": nm.result.matched,
                                "confidence": nm.result.confidence,
                                "message": nm.result.message,
                                "error": nm.result.error,
                                "metadata": nm.result.metadata,
                            },
                            "control_execution_id": nm.control_execution_id,
                            "execution_duration_ms": nm.execution_duration_ms,
                            "steering_context": (
                                {"message": nm.steering_context.message}
                                if nm.steering_context else None
                            ),
                        }
                        for nm in (result.non_matches or [])
                    ] if result.non_matches else None,
                }
            except Exception as e:
                logger.warning(
                    "Local evaluation failed: %s. Falling back to server-only evaluation.",
                    e,
                )

        # Fallback: server-only evaluation
        payload = {
            "agent_name": str(agent_name),
            "step": step,
            "stage": stage,
        }
        if target_type is not None and target_id is not None:
            payload["target_type"] = target_type
            payload["target_id"] = target_id

        response = await _post_evaluation_request(
            client,
            request_payload=payload,
            headers=headers,
            target_type=target_type,
            target_id=target_id,
        )
        response.raise_for_status()
        result_dict: dict[str, Any] = response.json()
        return result_dict


def _unexpected_control_failure_message(stage: str, error: Exception) -> str:
    """Build a user-facing message for unexpected control evaluation failures."""
    if stage == "pre":
        return (
            "Control check failed unexpectedly before execution. "
            f"Execution blocked for safety. Error: {error}"
        )
    return (
        "Control check failed unexpectedly after execution. "
        f"Result blocked for safety. Error: {error}"
    )


async def _run_control_check(
    ctx: ControlContext,
    stage: str,
    payload: dict[str, Any],
    controls: list[dict[str, Any]] | None,
) -> None:
    """Run one control stage and enforce fail-closed behavior on unexpected errors."""
    try:
        result = await _evaluate(
            ctx.agent_name,
            payload,
            stage,
            ctx.server_url,
            ctx.trace_id,
            ctx.span_id,
            controls=controls,
            event_agent_name=ctx.agent_name,
        )
        ctx.process_result(result, stage)
    except (ControlViolationError, ControlSteerError):
        raise
    except _InvalidToolsConfigurationError:
        raise
    except Exception as e:
        stage_name = "Pre" if stage == "pre" else "Post"
        logger.error("%s-execution control check failed: %s", stage_name, e, exc_info=True)
        raise RuntimeError(_unexpected_control_failure_message(stage, e)) from e


def _extract_input_from_args(func: Callable, args: tuple, kwargs: dict) -> str:
    """
    Extract input data from function arguments.

    Tries common parameter names, then falls back to first string argument.
    """
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    # Common input parameter names (in order of preference)
    input_names = ["input", "message", "query", "text", "prompt", "content", "user_input"]

    for name in input_names:
        if name in bound.arguments:
            value = bound.arguments[name]
            if value is not None:
                return str(value)

    # Fall back to first string argument
    for param_name, value in bound.arguments.items():
        if isinstance(value, str):
            return value

    # Last resort: stringify all arguments
