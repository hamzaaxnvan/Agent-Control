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
