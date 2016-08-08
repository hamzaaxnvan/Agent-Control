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
    )


class StepRecorder:
    """Mutable builder for one ``Step`` node and its children.

    ``Step`` itself is frozen, so this accumulates state and only
    constructs the real (frozen) ``Step`` in :meth:`build`.
    """

    def __init__(
        self,
        step_type: str,
        name: str,
        *,
        input: Any | None = None,
        context: dict[str, Any] | None = None,
        tools: list[JSONObject] | None = None,
        ground_truth: JSONValue | None = None,
        container_types: frozenset[str] = frozenset(),
        _parent: StepRecorder | None = None,
    ) -> None:
        self.type = ensure_step_type(step_type)
        self.name = name
        self.input = input
        self.output: Any | None = None
        self.context: dict[str, Any] | None = dict(context) if context is not None else None
        self.tools = tools
        self.ground_truth = ground_truth
        self._children: list[Step] = []
        self._parent = _parent
        self._container_types = container_types

    def __enter__(self) -> StepRecorder:
        return self

    def __exit__(
        self, exc_type: object, exc_value: BaseException | None, traceback: object
    ) -> None:
        if exc_value is not None:
            self.context = {**(self.context or {}), "error": repr(exc_value)}
        if self._parent is not None:
            self._parent._children.append(self.build())

    def child(
        self,
        step_type: str,
        name: str,
        *,
        input: Any | None = None,
        context: dict[str, Any] | None = None,
        tools: list[JSONObject] | None = None,
