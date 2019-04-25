"""Evaluation check operations for Agent Control SDK."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Any, Literal, cast

import httpx
from agent_control_engine import list_evaluators
from agent_control_engine.core import ControlEngine
from agent_control_models import (
    ControlDefinitionRuntime,
    ControlMatch,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationResult,
    EvaluatorResult,
    JSONValue,
    Step,
)

from ._state import state
from .client import AgentControlClient
from .evaluation_events import build_control_execution_events, enqueue_observability_events
from .observability import is_observability_enabled
from .tracing import get_trace_and_span_ids
from .validation import ensure_agent_name, ensure_step_type

_RuntimePostEvaluation = Callable[..., Awaitable[httpx.Response]]


@dataclass
class _ControlAdapter:
    """Adapts a control dict (from initAgent) to the ControlWithIdentity protocol."""

    id: int
    name: str
    control: ControlDefinitionRuntime


def _validate_target_pair(target_type: str | None, target_id: str | None) -> None:
    """Reject half-supplied target pairs; both or neither must be present."""
    if (target_type is None) != (target_id is None):
        raise ValueError("target_type and target_id must be supplied together.")


def _resolve_session_target(
    target_type: str | None, target_id: str | None
) -> tuple[str | None, str | None]:
    """Default per-call target from state, and reject mismatches.

    The SDK supports one target per session, fixed at ``init()`` time -
    including no-target sessions, where the session target is
    ``(None, None)``. The cached controls (``state.server_controls``) are
    fetched for that session target. A per-call override that disagrees
    with the session target - including supplying an explicit target on a
    no-target session - would evaluate against the wrong cache and could
    return safe without contacting the server. Reject the mismatch so
    callers re-init when they need to change targets.

    This rule applies to the session-bound entry point only
    (``evaluate_controls``). Lower-level helpers that accept their own
    client and controls are not session-bound and run the lighter
    :func:`_validate_target_pair` check instead.

    Returns the resolved ``(target_type, target_id)`` to forward.
    """
    if target_type is None and target_id is None:
        return state.target_type, state.target_id
    _validate_target_pair(target_type, target_id)
    if state.current_agent is not None and (
        target_type != state.target_type or target_id != state.target_id
    ):
        raise ValueError(
            "Per-call target context must match the target context fixed at "
            "init() time. The SDK supports one target per session "
            "(including no-target sessions); re-init to change it."
        )
    return target_type, target_id


def _get_applicable_controls(
    controls: list[_ControlAdapter],
    request: EvaluationRequest,
    *,
    context: Literal["sdk", "server"],
) -> list[_ControlAdapter]:
    """Return parsed controls that apply to this request in the given context."""
    applicable_controls = ControlEngine(
        controls,
        context=context,
    ).get_applicable_controls(request)
    return cast(list[_ControlAdapter], applicable_controls)


def _build_server_control_lookup(
    server_control_payloads: list[dict[str, Any]],
) -> dict[int, ControlDefinitionRuntime]:
    """Build a best-effort lookup of server control definitions."""
    control_lookup: dict[int, ControlDefinitionRuntime] = {}

    for control in server_control_payloads:
        ctrl_data = control.get("control", {})
        if (
            isinstance(ctrl_data, dict)
            and ctrl_data.get("template") is not None
            and ctrl_data.get("condition") is None
        ):
            continue

        try:
            control_lookup[control["id"]] = ControlDefinitionRuntime.model_validate(ctrl_data)
        except Exception:
            continue

    return control_lookup


def _has_applicable_prefiltered_server_controls(
    server_control_payloads: list[dict[str, Any]],
    request: EvaluationRequest,
) -> bool:
    """Return whether any partitioned server control applies to this request."""
    parsed_server_controls: list[_ControlAdapter] = []

    for control in server_control_payloads:
        # Skip unrendered template controls - they have no condition to evaluate
        # and should not trigger the server-call fallback.
        ctrl_data = control.get("control", {})
        if (
            isinstance(ctrl_data, dict)
            and ctrl_data.get("template") is not None
            and ctrl_data.get("condition") is None
        ):
            continue

        try:
            control_def = ControlDefinitionRuntime.model_validate(ctrl_data)
            parsed_server_controls.append(
                _ControlAdapter(
                    id=control["id"],
                    name=control["name"],
                    control=control_def,
                )
            )
        except Exception:
            return True

    if not parsed_server_controls:
        return False

    return bool(
        _get_applicable_controls(
            parsed_server_controls,
            request,
            context="server",
