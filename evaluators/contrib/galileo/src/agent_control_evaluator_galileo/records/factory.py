"""Build public Galileo records from Agent Control evaluation inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_control_models import Step
from galileo_core.schemas.logging.session import Session
from galileo_core.schemas.logging.span import (
    AgentSpan,
    ControlSpan,
    LlmSpan,
    RetrieverSpan,
    ToolSpan,
    WorkflowSpan,
)
from galileo_core.schemas.logging.trace import Trace

from .normalization import GalileoRecordNormalizer

type GalileoRecord = LlmSpan | ToolSpan | RetrieverSpan | Trace | Session
type GalileoSpan = LlmSpan | ToolSpan | RetrieverSpan
type GalileoCoreSpan = AgentSpan | WorkflowSpan | LlmSpan | RetrieverSpan | ToolSpan | ControlSpan
_MISSING = object()
_SPAN_TYPES = {"llm", "tool", "retriever"}
_RECORD_TYPES = _SPAN_TYPES | {"trace", "session"}


class RecordFactoryError(ValueError):
    """Base error raised when an Agent Control step cannot become a record."""


class UnsupportedStepTypeError(RecordFactoryError):
    """Raised when a step type has no supported public Galileo record."""


def _mapping(value: Any) -> Mapping[str, Any] | None:
    """Return mapping values unchanged, or ``None`` for non-mapping inputs."""
    return value if isinstance(value, Mapping) else None


def _selected_values(
    selected_data: Any,
    *,
    payload_field: str,
) -> tuple[Any, Any]:
    if isinstance(selected_data, Mapping) and (
        "input" in selected_data or "output" in selected_data
    ):
        return selected_data.get("input"), selected_data.get("output")
    if payload_field == "output":
        return None, selected_data
    return selected_data, None


def _span_children(children: list[GalileoRecord], *, parent_type: str) -> list[GalileoCoreSpan]:
    spans: list[GalileoCoreSpan] = []
    for child in children:
        if not isinstance(child, (LlmSpan, ToolSpan, RetrieverSpan)):
            raise RecordFactoryError(f"Galileo {parent_type} children must be span steps.")
        spans.append(child)
    return spans


def record_from_step(
    step: Step,
    *,
    selected_input: Any = _MISSING,
    selected_output: Any = _MISSING,
    selected_data: Any = _MISSING,
    payload_field: str = "input",
) -> GalileoRecord:
    """Build a canonical Galileo record from a complete Agent Control step.

    The complete step determines the record discriminator. Selector-selected
    values override only the corresponding input/output fields, preserving the
    selected evaluator payload while the unselected side comes from ``step``.
    Trace and session records require child steps; scalar selected
    values are never promoted into those record types. The result is a concrete
    Galileo Core step model (a ``BaseStep`` subclass) that can be JSON-serialized
    and revalidated using that subtype's schema. The factory doesn't assign
    execution IDs or storage ownership fields.
    """
    if not isinstance(step, Step):
        raise RecordFactoryError("A complete Agent Control Step is required.")
    record_type = step.type.strip().lower()
    if record_type not in _RECORD_TYPES:
        raise UnsupportedStepTypeError(f"Unsupported Agent Control step type: {step.type!r}")

    if selected_data is not _MISSING:
        selected_input, selected_output = _selected_values(
            selected_data,
            payload_field=payload_field,
        )
    context = dict(_mapping(step.context) or {})
    hierarchy_fields = {"children", "spans", "traces"}.intersection(context)
    if hierarchy_fields:
        fields = ", ".join(sorted(hierarchy_fields))
