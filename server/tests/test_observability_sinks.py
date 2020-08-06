"""Tests for server-side observability sink resolution."""

import pytest
from agent_control_telemetry import (
    REGISTERED_CONTROL_EVENT_SINK_NAME,
    ControlEventSinkSelection,
)

from agent_control_server.observability.sinks import (
    ResolvedControlEventBackend,
    get_registered_control_event_sink_factory_names,
    register_control_event_sink_factory,
    resolve_control_event_backend,
    unregister_control_event_sink_factory,
)


class DummyAsyncSink:
    async def write_events(self, events):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class DummyStore:
    async def store(self, events, *, namespace_key: str):  # type: ignore[no-untyped-def]
