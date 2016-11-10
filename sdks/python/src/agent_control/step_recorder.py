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
        ground_truth: JSONValue | None = None,
        container_types: Collection[str] | None = None,
    ) -> StepRecorder:
        """Start a nested recorder; it attaches to this node on ``__exit__``.

        Inherits this node's ``container_types`` unless ``container_types``
        is given explicitly.
        """
        return StepRecorder(
            step_type,
            name,
            input=input,
            context=context,
            tools=tools,
            ground_truth=ground_truth,
            container_types=(
                self._container_types if container_types is None else frozenset(container_types)
            ),
            _parent=self,
        )

    def add(self, step: Step | Mapping[str, Any]) -> None:
        """Attach an already-built child step."""
        self._children.append(step if isinstance(step, Step) else Step.model_validate(step))

    def _record_call_result(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        output: Any,
        step_name: str | None,
        step_type: str | None,
        tools: ToolsConfiguration,
        step_context: dict[str, Any] | None,
        error: BaseException | None,
    ) -> None:
        payload = _create_evaluation_payload(
            func, args, kwargs, output, step_name, step_type, tools
        )
        context = {**(payload.get("context") or {}), **(step_context or {})}
        if error is not None:
            context["error"] = repr(error)
        if context:
            payload["context"] = context
        self._children.append(Step.model_validate(payload))

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        step_type: str | None = None,
        step_name: str | None = None,
        tools: ToolsConfiguration = None,
        step_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> T:
        """Run ``func``, record it via ``@control()``'s capture logic, return its output.

        ``step_context`` is merged into the recorded child's ``context`` (an
        ``error`` key added on failure takes precedence over the same key in
        ``step_context``). It is named ``step_context`` rather than ``context``
        so it can't collide with a ``context`` keyword argument on ``func``
        itself, which ``**kwargs`` would otherwise forward unchanged.
        """
        try:
            output = func(*args, **kwargs)
        except Exception as exc:
            self._record_call_result(
                func, args, kwargs, None, step_name, step_type, tools, step_context, exc
            )
            raise
        self._record_call_result(
            func, args, kwargs, output, step_name, step_type, tools, step_context, None
        )
        return output

    async def acall(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        step_type: str | None = None,
        step_name: str | None = None,
        tools: ToolsConfiguration = None,
        step_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> T:
        """Async counterpart to :meth:`call`."""
        try:
            output = await func(*args, **kwargs)
        except Exception as exc:
            self._record_call_result(
                func, args, kwargs, None, step_name, step_type, tools, step_context, exc
            )
            raise
        self._record_call_result(
            func, args, kwargs, output, step_name, step_type, tools, step_context, None
        )
        return output

    def build(self) -> Step:
        """Recursively construct the frozen ``Step`` for this node and its children."""
        input_value = self.input
        if input_value is None and self.type == STEP_TYPE_TOOL:
