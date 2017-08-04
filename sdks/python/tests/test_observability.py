"""Tests for the observability module (EventBatcher)."""

import asyncio
import logging
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agent_control_models import ControlExecutionEvent
from agent_control_telemetry import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
)
from agent_control_telemetry.sinks import BaseControlEventSink, SinkResult

from agent_control.observability import (
    EventBatcher,
    add_event,
    get_event_batcher,
    get_event_sink,
    get_registered_control_event_sink_factory_names,
    get_registered_control_event_sinks,
    init_observability,
    is_observability_enabled,
    log_span_end,
    log_span_start,
    register_control_event_sink,
    register_control_event_sink_factory,
    shutdown_observability,
    sync_shutdown_observability,
    unregister_control_event_sink,
    write_events,
)
from agent_control.otel_sink import OTEL_CONTROL_EVENT_SINK_NAME
from agent_control.settings import SDKSettings, configure_settings, get_settings
from agent_control_models import ControlExecutionEvent
from agent_control_telemetry import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
)
from agent_control_telemetry.sinks import BaseControlEventSink, SinkResult


def create_mock_event():
    """Create a mock ControlExecutionEvent for testing."""
    mock_event = MagicMock()
    mock_event.model_dump = MagicMock(return_value={
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "agent_name": "test-agent",
        "control_id": 1,
        "control_name": "test-control",
        "check_stage": "pre",
        "applies_to": "llm_call",
        "action": "observe",
        "matched": False,
        "confidence": 0.95,
        "timestamp": datetime.now(UTC).isoformat(),
    })
    return mock_event


class RecordingSink(BaseControlEventSink):
    """Test sink that records the exact event batches it receives."""

    def __init__(self, *, accepted: int | None = None):
        self.accepted = accepted
        self.received_batches: list[list[ControlExecutionEvent]] = []

    def write_events(self, events: Sequence[ControlExecutionEvent]) -> SinkResult:
        self.received_batches.append(list(events))
        accepted = self.accepted if self.accepted is not None else len(events)
        dropped = max(len(events) - accepted, 0)
        return SinkResult(accepted=accepted, dropped=dropped)


class LifecycleRecordingSink(RecordingSink):
    """Test sink that records shutdown lifecycle hooks."""

    def __init__(self) -> None:
        super().__init__()
        self.flush_calls = 0
        self.close_calls = 0

    def flush(self) -> None:
        self.flush_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class AsyncLifecycleRecordingSink(RecordingSink):
    """Test sink with async shutdown lifecycle hooks."""

    def __init__(self) -> None:
        super().__init__()
        self.flush_calls = 0
        self.close_calls = 0

    async def flush(self) -> None:
        self.flush_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


def reset_observability_state() -> None:
    """Clear global observability state between tests."""
    import agent_control.observability as obs

    obs._batcher = None
    obs._event_sink = None
    obs._configured_named_event_sink = None
    obs._configured_named_event_sink_selection = None
    configure_settings(
        observability_enabled=True,
        observability_sink_name=DEFAULT_CONTROL_EVENT_SINK_NAME,
        observability_sink_config={},
        api_key_header="X-API-Key",
    )
    with obs._used_custom_event_sinks_lock:
        obs._used_custom_event_sinks.clear()
    with obs._external_event_sinks_lock:
        obs._external_event_sinks.clear()
    for name in obs.get_registered_control_event_sink_factory_names():
        obs.unregister_control_event_sink_factory(name)
    obs._register_builtin_control_event_sink_factories()


class TestEventBatcherInit:
    """Tests for EventBatcher initialization."""

    def test_init_default_values(self):
        """Test EventBatcher initializes with default values."""
        batcher = EventBatcher()
        assert batcher.api_key_header == get_settings().api_key_header
        assert batcher.batch_size == get_settings().batch_size
        assert batcher.flush_interval == get_settings().flush_interval
        assert batcher.shutdown_join_timeout == get_settings().shutdown_join_timeout
        assert batcher.shutdown_flush_timeout == get_settings().shutdown_flush_timeout
        assert batcher.shutdown_max_failed_flushes == get_settings().shutdown_max_failed_flushes
        assert batcher._running is False
        assert batcher._events == []

    def test_init_custom_values(self):
        """Test EventBatcher initializes with custom values."""
        batcher = EventBatcher(
            server_url="http://custom:9000",
            api_key="test-key",
            api_key_header="X-Custom-API-Key",
            batch_size=50,
            flush_interval=5.0,
        )
        assert batcher.server_url == "http://custom:9000"
        assert batcher.api_key == "test-key"
        assert batcher.api_key_header == "X-Custom-API-Key"
        assert batcher.batch_size == 50
        assert batcher.flush_interval == 5.0

    def test_init_from_settings(self):
        """Test EventBatcher reads from settings."""
        from agent_control.settings import configure_settings

        original_settings = get_settings().model_dump()

        try:
            # Configure settings programmatically
            configure_settings(
                url="http://configured-server:8080",
                api_key="configured-api-key",
                api_key_header="X-Custom-API-Key",
            )

            batcher = EventBatcher()
            assert batcher.server_url == "http://configured-server:8080"
            assert batcher.api_key == "configured-api-key"
            assert batcher.api_key_header == "X-Custom-API-Key"
        finally:
            # Restore original settings
            configure_settings(**original_settings)


class TestEventBatcherStartStop:
    """Tests for EventBatcher start/stop lifecycle."""

    def test_start_sets_running(self):
        """Test that start sets running flag."""
        batcher = EventBatcher()
        batcher.start()
        assert batcher._running is True
        batcher.stop()

    def test_stop_clears_running(self):
        """Test that stop clears running flag."""
        batcher = EventBatcher()
        batcher.start()
        batcher.stop()
        assert batcher._running is False

    def test_double_start_is_safe(self):
        """Test that calling start twice is safe."""
        batcher = EventBatcher()
        batcher.start()
        batcher.start()  # Should not raise
        assert batcher._running is True
        batcher.stop()

    def test_stop_without_start_is_safe(self):
        """Test that calling stop without start is safe."""
        batcher = EventBatcher()
        batcher.stop()  # Should not raise
        assert batcher._running is False


class TestEventBatcherWorkerThread:
    """Tests for EventBatcher dedicated worker thread."""

    def test_start_creates_worker_thread(self):
        """Test that start() creates a dedicated daemon thread with its own loop."""
        batcher = EventBatcher()
        batcher.start()
        assert batcher._running is True
        assert batcher._thread is not None
        assert batcher._thread.is_alive()
        assert batcher._thread.daemon is True
        assert batcher._loop is not None
        assert not batcher._loop.is_closed()
        batcher.stop()

    def test_sync_repeated_asyncio_run_still_flushes(self):
        """Test that events flush even across repeated asyncio.run() calls.

        Reproduces the sync @control flow: sync_wrapper calls asyncio.run()
        per invocation, creating and closing a caller loop each time. The
        batcher's dedicated thread should be unaffected.
        """
        import time

        batcher = EventBatcher(batch_size=100, flush_interval=0.1)
        batcher._send_batch = AsyncMock(return_value=True)
        batcher.start()

        # Simulate three sync_wrapper-style calls, each with its own asyncio.run()
        for _ in range(3):
            batcher.add_event(create_mock_event())
            # Each sync_wrapper call creates and closes a caller loop
            asyncio.run(asyncio.sleep(0))

        # Wait for the flush interval to fire on the worker thread
        time.sleep(0.3)

        assert batcher._events_sent == 3
        assert len(batcher._events) == 0
        batcher.stop()

    def test_worker_loop_survives_caller_loop_closures(self):
        """Test that worker loop is unaffected by caller loops being closed."""
        batcher = EventBatcher(batch_size=100, flush_interval=0.1)
        batcher._send_batch = AsyncMock(return_value=True)
        batcher.start()

        worker_loop = batcher._loop

        # Create and close several caller loops - should not affect worker
        for _ in range(3):
            loop = asyncio.new_event_loop()
            loop.close()

        assert batcher._loop is worker_loop
        assert not batcher._loop.is_closed()

        batcher.add_event(create_mock_event())
        batcher.add_event(create_mock_event())

        import time
        time.sleep(0.3)

        assert batcher._events_sent == 2
        batcher.stop()

    def test_shutdown_flushes_and_joins_thread(self):
        """Test that shutdown() flushes remaining events and joins the worker thread."""
        batcher = EventBatcher(batch_size=100, flush_interval=60.0)
        batcher._send_batch = AsyncMock(return_value=True)
        batcher.start()

        for _ in range(5):
            batcher.add_event(create_mock_event())

        assert len(batcher._events) == 5

        batcher.shutdown()

        assert batcher._events_sent == 5
        assert len(batcher._events) == 0
        assert not batcher._running
        assert batcher._thread is None

    def test_shutdown_flushes_when_worker_not_running(self):
        """Test that shutdown() still flushes when the worker thread is not running."""
        batcher = EventBatcher(batch_size=100, flush_interval=60.0)

        for _ in range(5):
            batcher.add_event(create_mock_event())

        with patch.object(batcher, "_send_batch_sync", return_value=True):
            batcher.shutdown()

        assert batcher._events_sent == 5
        assert len(batcher._events) == 0
        assert batcher._events_dropped == 0
        assert batcher._thread is None

    def test_shutdown_uses_sync_fallback_when_worker_not_running(self):
        """Shutdown should use the sync fallback path without relying on asyncio."""
        batcher = EventBatcher(batch_size=100, flush_interval=60.0)

        for _ in range(5):
            batcher.add_event(create_mock_event())

        batcher._client = AsyncMock()

        with patch.object(batcher, "_send_batch_sync", return_value=True) as send_batch_sync:
            batcher.shutdown()

        send_batch_sync.assert_called_once()
        assert batcher._events_sent == 5
        assert len(batcher._events) == 0
        # The sync fallback only promises to drop the stale AsyncClient reference.
        assert batcher._client is None

    def test_shutdown_drains_inflight_flush_without_data_loss(self):
        """Test that shutdown waits for in-flight flushes and sends all events."""
        import time

        batcher = EventBatcher(batch_size=100, flush_interval=60.0)

        async def slow_send(events):
            await asyncio.sleep(0.05)
            return True

        batcher._send_batch = slow_send
        batcher.start()

        # Trigger multiple flushes and allow one to start before shutdown.
        for _ in range(350):
            batcher.add_event(create_mock_event())
        time.sleep(0.02)

        batcher.shutdown()

        assert batcher._events_sent == 350
        assert len(batcher._events) == 0
        assert batcher._events_dropped == 0


class TestEventBatcherAddEvent:
    """Tests for adding events to the batcher."""

    def test_add_event_success(self):
        """Test adding an event successfully."""
        batcher = EventBatcher()
        event = create_mock_event()

        result = batcher.add_event(event)

        assert result is True
        assert len(batcher._events) == 1

    def test_add_multiple_events(self):
        """Test adding multiple events."""
        batcher = EventBatcher()
        events = [create_mock_event() for _ in range(5)]

        for event in events:
            batcher.add_event(event)

        assert len(batcher._events) == 5

    def test_add_event_drops_when_queue_full(self):
        """Test that events are dropped when queue is full."""
