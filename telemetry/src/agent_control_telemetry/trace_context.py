"""Provider-agnostic trace context interface for external tracing systems."""

from collections.abc import Callable
from typing import TypedDict


class TraceContext(TypedDict):
    """Resolved trace context for a control evaluation."""

    trace_id: str
    span_id: str


