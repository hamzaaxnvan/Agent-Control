"""Incremental builder for ``Step`` trees (trace/session-level evaluation).

Manually populating ``Step.children`` for a trace or session means building
the whole tree by hand before calling ``evaluate_controls``/``evaluate_step``.
``StepRecorder`` lets callers build that tree as they execute instead: each
nested call is appended to its parent as it happens, with no intermediate
dict representation and no separate converter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from typing import Any, Literal, TypeVar

from agent_control_models import STEP_TYPE_TOOL, EvaluationResult, JSONObject, JSONValue, Step

from ._state import state
from .control_decorators import ToolsConfiguration, _create_evaluation_payload
from .evaluation import evaluate_step
from .validation import ensure_step_type

T = TypeVar("T")


def record_step(
    step_type: str,
    name: str,
    *,
    input: Any | None = None,
    context: dict[str, Any] | None = None,
    tools: list[JSONObject] | None = None,
    ground_truth: JSONValue | None = None,
    container_types: Collection[str] = (),
) -> StepRecorder:
    """Start building a ``Step`` tree. Use as a context manager.

    ``container_types`` names step types whose ``children`` should be
    serialized as ``[]`` rather than omitted when none were recorded - e.g.
    a trace/session that legitimately ran with zero children, as opposed to
    a leaf type for which children isn't a meaningful concept at all. Step
    types are caller-defined strings, so this isn't assumed; opt in with
    e.g. ``container_types={"trace", "session"}``. Inherited by nested
    ``.child()`` recorders unless overridden there.
    """
    return StepRecorder(
        step_type,
        name,
        input=input,
        context=context,
        tools=tools,
        ground_truth=ground_truth,
        container_types=frozenset(container_types),
