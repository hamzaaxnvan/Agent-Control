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
        return len(events)

    async def query_stats(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def query_events(self, query, *, namespace_key: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def close(self) -> None:
        return None


def teardown_function() -> None:
    for name in get_registered_control_event_sink_factory_names():
        unregister_control_event_sink_factory(name)


def test_resolve_control_event_backend_uses_default_backend_for_default_selection() -> None:
    default_backend = ResolvedControlEventBackend(
        sink=DummyAsyncSink(),
        event_store=DummyStore(),
    )

    resolved = resolve_control_event_backend(
        ControlEventSinkSelection(name="default"),
