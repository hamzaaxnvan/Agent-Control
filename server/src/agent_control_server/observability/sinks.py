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

    async def write_events(
        self,
        events: Sequence[ControlExecutionEvent],
        *,
        namespace_key: str,
    ) -> SinkResult:
        """Write events to the underlying store and report accepted/dropped counts."""
        stored = await self.store.store(list(events), namespace_key=namespace_key)
        dropped = max(len(events) - stored, 0)
        return SinkResult(accepted=stored, dropped=dropped)


ServerControlEventSink = AsyncControlEventSink | EventStoreControlEventSink


@dataclass(frozen=True)
class ResolvedControlEventBackend:
    """Server observability backend with aligned write and query dependencies."""

    sink: ServerControlEventSink
    event_store: EventStore


def register_control_event_sink_factory(
    name: str,
    factory: ControlEventSinkFactory[ResolvedControlEventBackend],
) -> None:
    """Register a named server observability backend factory for sink selection."""
    _named_event_sink_factories.register(name, factory)


def unregister_control_event_sink_factory(name: str) -> None:
    """Unregister a named async control-event sink factory."""
