"""Server-side sink implementations for observability event delivery."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agent_control_models.observability import ControlExecutionEvent
from agent_control_telemetry import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
    AsyncControlEventSink,
    ControlEventSinkFactory,
    ControlEventSinkFactoryRegistry,
    ControlEventSinkSelection,
    SinkResult,
)
from agent_control_telemetry.sink_selection import SinkSelectionError

from .store.base import EventStore

_named_event_sink_factories: ControlEventSinkFactoryRegistry[ResolvedControlEventBackend] = (
    ControlEventSinkFactoryRegistry()
)


class EventStoreControlEventSink:
    """Write events through an EventStore-backed sink."""

    def __init__(self, store: EventStore):
        self.store = store

