from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap

from agent_control_server import main as main_module
from agent_control_server.config import observability_settings, settings
from agent_control_server.main import lifespan
from agent_control_server.observability.sinks import (
    ResolvedControlEventBackend,
    register_control_event_sink_factory,
    unregister_control_event_sink_factory,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_importing_main_does_not_configure_host_owned_logging() -> None:
    script = textwrap.dedent(
        """
        import json
        import logging

        root = logging.getLogger()
        handler = logging.StreamHandler()
        handler.setLevel(logging.ERROR)
        root.handlers = [handler]
        root.setLevel(logging.WARNING)

        before = {
            "handler_types": [type(h).__name__ for h in root.handlers],
            "handler_levels": [h.level for h in root.handlers],
            "root_level": root.level,
        }
        import agent_control_server.main
        after = {
            "handler_types": [type(h).__name__ for h in root.handlers],
            "handler_levels": [h.level for h in root.handlers],
            "root_level": root.level,
        }
        print(json.dumps({"before": before, "after": after}))
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "AGENT_CONTROL_CONFIGURE_LOGGING": "false"},
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["before"] == payload["after"]


def test_configure_logging_once_is_idempotent(monkeypatch) -> None:
    calls: list[str] = []

    def fake_configure_logging(*, default_level: str) -> None:
        calls.append(default_level)

    monkeypatch.setattr(main_module, "_logging_configured", False)
    monkeypatch.setattr(main_module, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(settings, "debug", False)

    main_module._configure_logging_once()
    main_module._configure_logging_once()

    assert calls == ["INFO"]


def test_lifespan_initializes_observability_when_enabled(monkeypatch) -> None:
    # Given: observability enabled
    monkeypatch.setattr(observability_settings, "enabled", True)
    monkeypatch.setattr(observability_settings, "sink_name", "default")

    app = FastAPI(lifespan=lifespan)

    # When: the app starts
    with TestClient(app):
        # Then: observability components are initialized
        assert hasattr(app.state, "event_store")
        assert hasattr(app.state, "event_ingestor")
        assert app.state.event_ingestor.sink.store is app.state.event_store


def test_lifespan_uses_custom_backend_store_for_custom_sink(monkeypatch) -> None:
    class DummyStore:
        def __init__(self) -> None:
            self.closed = False

        async def store(self, events, *, namespace_key: str):  # type: ignore[no-untyped-def]
            return len(events)

        async def query_stats(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def query_events(self, query, *, namespace_key: str):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def close(self) -> None:
            self.closed = True

    class DummySink:
        def __init__(self) -> None:
            self.flushed = False
            self.closed = False

        async def write_events(self, events):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def flush(self) -> None:
            self.flushed = True

        async def close(self) -> None:
            self.closed = True

    custom_store = DummyStore()
    custom_sink = DummySink()

    monkeypatch.setattr(observability_settings, "enabled", True)
    monkeypatch.setattr(observability_settings, "sink_name", "custom")
    monkeypatch.setattr(observability_settings, "sink_config", {"target": "demo"})
    monkeypatch.setattr(
        main_module,
        "PostgresEventStore",
        lambda session_maker: (_ for _ in ()).throw(
            AssertionError("default store should not be created")
        ),
    )
    register_control_event_sink_factory(
        "custom",
        lambda config: ResolvedControlEventBackend(
            sink=custom_sink,
            event_store=custom_store,
        ),
    )

    app = FastAPI(lifespan=lifespan)

    try:
        with TestClient(app):
            assert app.state.event_store is custom_store
            assert app.state.event_ingestor.sink is custom_sink
            assert app.state.event_sink is custom_sink
        assert custom_store.closed is True
        assert custom_sink.flushed is True
        assert custom_sink.closed is True
    finally:
        unregister_control_event_sink_factory("custom")


def test_lifespan_flushes_shared_sink_store_backend(monkeypatch) -> None:
    class SharedBackend:
        def __init__(self) -> None:
            self.flushed = False
            self.closed = 0

        async def write_events(self, events):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def store(self, events, *, namespace_key: str):  # type: ignore[no-untyped-def]
            return len(events)

        async def query_stats(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def query_events(self, query, *, namespace_key: str):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def flush(self) -> None:
            self.flushed = True

        async def close(self) -> None:
            self.closed += 1

    backend = SharedBackend()

    monkeypatch.setattr(observability_settings, "enabled", True)
    monkeypatch.setattr(observability_settings, "sink_name", "custom")
    monkeypatch.setattr(observability_settings, "sink_config", {"target": "demo"})
    register_control_event_sink_factory(
        "custom",
        lambda config: ResolvedControlEventBackend(
            sink=backend,
            event_store=backend,
        ),
    )

    app = FastAPI(lifespan=lifespan)

    try:
        with TestClient(app):
            assert app.state.event_store is backend
            assert app.state.event_sink is backend
            assert app.state.event_ingestor.sink is backend
        assert backend.flushed is True
        assert backend.closed == 1
    finally:
        unregister_control_event_sink_factory("custom")


def test_lifespan_skips_observability_when_disabled(monkeypatch) -> None:
    # Given: observability disabled
    monkeypatch.setattr(observability_settings, "enabled", False)

    app = FastAPI(lifespan=lifespan)

    # When: the app starts
    with TestClient(app):
        # Then: observability components are not initialized
        assert not hasattr(app.state, "event_store")
        assert not hasattr(app.state, "event_ingestor")


def test_lifespan_fails_open_when_out_of_box_bootstrap_fails(monkeypatch, caplog) -> None:
    async def fail_seed_out_of_box_controls(**kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(observability_settings, "enabled", False)
    monkeypatch.setattr(main_module, "seed_out_of_box_controls", fail_seed_out_of_box_controls)

    app = FastAPI(lifespan=lifespan)

    with caplog.at_level("WARNING"):
        with TestClient(app):
            pass

    assert "Out-of-box control bootstrap failed; continuing startup" in caplog.text


def test_lifespan_times_out_blocked_out_of_box_bootstrap(monkeypatch, caplog) -> None:
    cancelled = False

    async def block_seed_out_of_box_controls(**kwargs: object) -> None:
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    monkeypatch.setattr(observability_settings, "enabled", False)
    monkeypatch.setattr(settings, "out_of_box_bootstrap_timeout_seconds", 0.01)
    monkeypatch.setattr(main_module, "seed_out_of_box_controls", block_seed_out_of_box_controls)

    app = FastAPI(lifespan=lifespan)

    with caplog.at_level("WARNING"):
        with TestClient(app):
            pass

    assert cancelled is True
    assert (
        "Out-of-box control bootstrap timed out after 0.01 seconds; continuing startup"
        in caplog.text
    )


def test_custom_openapi_replaces_jsonvalue_variants(monkeypatch) -> None:
    # Given: a custom openapi generator that includes Pydantic JSONValue schemas
    json_value_schema_names = (
        "JSONValue",
        "JSONValue-Input",
        "JSONValue-Output",
        "JsonValue",
        "JsonValue-Input",
        "JsonValue-Output",
    )

    def fake_get_openapi(*, title, version, description, routes):
        return {
            "components": {
                "schemas": {name: {"type": "object"} for name in json_value_schema_names}
            },
