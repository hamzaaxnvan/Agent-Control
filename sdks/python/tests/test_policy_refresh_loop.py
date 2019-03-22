"""Tests for SDK policy refresh loop lifecycle and cache publication semantics."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Generator
from unittest.mock import ANY, AsyncMock, call, patch

import agent_control
import pytest
from agent_control._state import state
from agent_control.settings import configure_settings, get_settings


@pytest.fixture(autouse=True)
def _reset_policy_refresh_state() -> Generator[None, None, None]:
    """Ensure refresh loop and cache globals do not leak across tests."""
    agent_control._stop_policy_refresh_loop()
    agent_control._reset_state()
    yield
    agent_control._stop_policy_refresh_loop()
    agent_control._reset_state()


def test_init_starts_policy_refresh_loop_by_default() -> None:
    # Given: init dependencies are mocked and no explicit refresh interval is passed.
    register_agent_mock = AsyncMock(return_value={"created": True, "controls": []})
    health_check_mock = AsyncMock(return_value={"status": "healthy"})

    # When: init() is called.
    with patch(
        "agent_control.__init__.AgentControlClient.health_check",
        new=health_check_mock,
    ), patch(
        "agent_control.__init__.agents.register_agent",
        new=register_agent_mock,
    ), patch(
        "agent_control._start_policy_refresh_loop",
    ) as start_loop_mock:
        agent_control.init(
            agent_name="default-refresh-agent",
        )

    # Then: the loop starts with the default interval (60s).
    start_loop_mock.assert_called_once_with(60)


def test_init_disables_policy_refresh_loop_when_interval_is_zero() -> None:
    # Given: init dependencies are mocked.
    register_agent_mock = AsyncMock(return_value={"created": True, "controls": []})
    health_check_mock = AsyncMock(return_value={"status": "healthy"})

    # When: init() is called with interval=0.
    with patch(
        "agent_control.__init__.AgentControlClient.health_check",
        new=health_check_mock,
    ), patch(
        "agent_control.__init__.agents.register_agent",
        new=register_agent_mock,
    ), patch(
        "agent_control._start_policy_refresh_loop",
    ) as start_loop_mock:
        agent_control.init(
            agent_name="disabled-refresh-agent",
            policy_refresh_interval_seconds=0,
        )

    # Then: no background loop is started.
    start_loop_mock.assert_not_called()


def test_reinit_stops_and_restarts_policy_refresh_loop() -> None:
    # Given: init dependencies are mocked.
    register_agent_mock = AsyncMock(return_value={"created": True, "controls": []})
    health_check_mock = AsyncMock(return_value={"status": "healthy"})

    # When: init() is called twice with different intervals.
    with patch(
        "agent_control.__init__.AgentControlClient.health_check",
        new=health_check_mock,
    ), patch(
        "agent_control.__init__.agents.register_agent",
        new=register_agent_mock,
    ), patch(
        "agent_control._stop_policy_refresh_loop",
    ) as stop_loop_mock, patch(
        "agent_control._start_policy_refresh_loop",
    ) as start_loop_mock:
        agent_control.init(
            agent_name="reinit-agent",
            policy_refresh_interval_seconds=60,
        )
        agent_control.init(
            agent_name="reinit-agent",
            policy_refresh_interval_seconds=5,
        )

    # Then: each init stops the old loop first and starts with the new interval.
    assert stop_loop_mock.call_count == 2
    assert start_loop_mock.call_args_list == [call(60), call(5)]


def test_reinit_without_sink_args_preserves_current_sink_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the environment uses the default sink selection.
    monkeypatch.delenv("AGENT_CONTROL_OBSERVABILITY_SINK_NAME", raising=False)
    monkeypatch.delenv("AGENT_CONTROL_OBSERVABILITY_SINK_CONFIG", raising=False)
    original_settings = get_settings().model_dump()
    configure_settings(observability_sink_name="default", observability_sink_config={})
    register_agent_mock = AsyncMock(return_value={"created": True, "controls": []})
    health_check_mock = AsyncMock(return_value={"status": "healthy"})

    try:
        # When: init() first selects a custom sink, then re-inits without sink kwargs.
        with patch(
            "agent_control.__init__.AgentControlClient.health_check",
            new=health_check_mock,
        ), patch(
            "agent_control.__init__.agents.register_agent",
            new=register_agent_mock,
        ), patch(
            "agent_control._stop_policy_refresh_loop",
        ), patch(
            "agent_control._start_policy_refresh_loop",
        ), patch(
            "agent_control.observability.EventBatcher.start",
        ) as batcher_start_mock:
            agent_control.init(
                agent_name="reinit-agent",
                observability_sink_name="registered",
                observability_sink_config={"project": "demo"},
            )
            agent_control.init(agent_name="reinit-agent")

        # Then: the second init preserves the SDK's current sink selection.
        settings = get_settings()
        assert settings.observability_sink_name == "registered"
        assert settings.observability_sink_config == {"project": "demo"}
        assert batcher_start_mock.call_count == 0
    finally:
        agent_control.shutdown()
        configure_settings(**original_settings)


def test_policy_refresh_worker_runs_multiple_iterations() -> None:
    # Given: a stop event that is set after the second fetch call.
    stop_event = threading.Event()
    call_count = 0

    async def mock_fetch() -> list[dict[str, int]]:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            stop_event.set()
        return [{"id": call_count}]

    # When: the worker loop runs with zero wait interval for deterministic test speed.
    with patch(
        "agent_control._fetch_controls_async",
        new=AsyncMock(side_effect=mock_fetch),
    ):
        agent_control._policy_refresh_worker(stop_event, interval_seconds=0)

    # Then: periodic refresh behavior is observed (more than one iteration).
    assert call_count >= 2


def test_publish_server_controls_clears_cache_on_none() -> None:
    # GIVEN: an existing cached controls snapshot.
    state.server_controls = [{"id": 1, "name": "cached"}]

    # WHEN: the publisher receives None.
    published = agent_control._publish_server_controls(None)

    # THEN: the cache is cleared and None is returned.
    assert published is None
    assert agent_control.get_server_controls() is None


def test_start_policy_refresh_loop_ignores_non_positive_interval() -> None:
    # GIVEN: no background refresh loop is running.
    assert agent_control._refresh_thread is None
    assert agent_control._refresh_stop_event is None

    # WHEN: loop start is requested with interval=0.
