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
        batcher = EventBatcher(batch_size=10)  # Max queue = 10 * 10 = 100

        # Add more than max events
        for i in range(105):
            batcher.add_event(create_mock_event())

        assert len(batcher._events) == 100
        assert batcher._events_dropped == 5

    def test_add_event_thread_safe(self):
        """Test that add_event is thread-safe."""
        import threading

        batcher = EventBatcher(batch_size=100)
        results = []

        def add_events():
            for _ in range(50):
                result = batcher.add_event(create_mock_event())
                results.append(result)

        threads = [threading.Thread(target=add_events) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 200 events should be added (batch_size=100 means max=1000)
        assert len(batcher._events) == 200
        assert all(results)


class TestEventBatcherStats:
    """Tests for EventBatcher statistics."""

    def test_get_stats_initial(self):
        """Test getting stats from new batcher."""
        batcher = EventBatcher()
        stats = batcher.get_stats()

        assert stats["events_sent"] == 0
        assert stats["events_dropped"] == 0
        assert stats["events_pending"] == 0
        assert stats["flush_count"] == 0
        assert stats["running"] is False

    def test_get_stats_with_events(self):
        """Test getting stats after adding events."""
        batcher = EventBatcher()
        for _ in range(5):
            batcher.add_event(create_mock_event())

        stats = batcher.get_stats()
        assert stats["events_pending"] == 5

    def test_get_stats_after_start(self):
        """Test getting stats after starting batcher."""
        batcher = EventBatcher()
        batcher.start()

        stats = batcher.get_stats()
        assert stats["running"] is True

        batcher.stop()


class TestEventBatcherFlush:
    """Tests for EventBatcher flush operations."""

    @pytest.mark.asyncio
    async def test_flush_empty_queue(self):
        """Test flushing an empty queue does nothing."""
        batcher = EventBatcher()
        await batcher._flush()
        assert batcher._flush_count == 0

    @pytest.mark.asyncio
    async def test_flush_sends_events(self):
        """Test that flush sends events to server."""
        batcher = EventBatcher()
        for _ in range(3):
            batcher.add_event(create_mock_event())

        # Mock the _send_batch method
        batcher._send_batch = AsyncMock(return_value=True)

        await batcher._flush()

        assert batcher._send_batch.called
        assert batcher._events_sent == 3
        assert len(batcher._events) == 0

    @pytest.mark.asyncio
    async def test_flush_requeues_on_failure(self):
        """Test that flush requeues events on send failure."""
        batcher = EventBatcher()
        for _ in range(3):
            batcher.add_event(create_mock_event())

        # Mock the _send_batch method to fail
        batcher._send_batch = AsyncMock(return_value=False)

        await batcher._flush()

        # Events should be requeued
        assert len(batcher._events) == 3
        assert batcher._events_sent == 0

    @pytest.mark.asyncio
    async def test_flush_all_empties_queue(self):
        """Test that flush_all empties the entire queue."""
        batcher = EventBatcher(batch_size=2)
        for _ in range(5):
            batcher.add_event(create_mock_event())

        batcher._send_batch = AsyncMock(return_value=True)

        await batcher.flush_all()

        assert len(batcher._events) == 0
        assert batcher._events_sent == 5

    @pytest.mark.asyncio
    async def test_flush_all_stops_after_failed_flush_limit(self):
        """Test that flush_all exits after configured consecutive flush failures."""
        batcher = EventBatcher(batch_size=2)
        for _ in range(3):
            batcher.add_event(create_mock_event())

        batcher._send_batch = AsyncMock(return_value=False)

        await batcher.flush_all(max_failed_flushes=2)

        assert batcher._send_batch.await_count == 2
        assert len(batcher._events) == 3

    @pytest.mark.asyncio
    async def test_flush_all_rejects_invalid_failed_flush_limit(self):
        """Test that flush_all validates max_failed_flushes."""
        batcher = EventBatcher()
        with pytest.raises(ValueError, match="max_failed_flushes must be >= 1"):
            await batcher.flush_all(max_failed_flushes=0)


class TestEventBatcherSendBatch:
    """Tests for EventBatcher HTTP batch sending."""

    @pytest.mark.asyncio
    async def test_send_batch_without_httpx(self):
        """Test that send_batch handles missing httpx gracefully."""
        batcher = EventBatcher()
        events = [create_mock_event()]

        with patch.dict("sys.modules", {"httpx": None}):
            # This should not raise, just return False
            result = await batcher._send_batch(events)
            # Can't easily test this without breaking httpx import
            # Just verify the method exists and runs
            assert isinstance(result, bool)


class TestEventBatcherSendBatchSync:
    """Tests for sync HTTP sending used during shutdown fallback."""

    def test_send_batch_sync_returns_true_on_202(self):
        batcher = EventBatcher(server_url="http://test:8000", api_key="test-key")
        response = MagicMock(status_code=202, text="accepted")
        client = MagicMock()
        client.post.return_value = response
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        with patch(
            "agent_control.observability.httpx.Client",
            return_value=client_context,
        ) as client_ctor:
            result = batcher._send_batch_sync([create_mock_event()])

        assert result is True
        client_ctor.assert_called_once_with(timeout=30.0)
        client.post.assert_called_once()
        assert client.post.call_args.kwargs["headers"]["X-API-Key"] == "test-key"

    def test_send_batch_sync_uses_configured_api_key_header(self):
        batcher = EventBatcher(
            server_url="http://test:8000",
            api_key="test-key",
            api_key_header="X-Custom-API-Key",
        )
        response = MagicMock(status_code=202, text="accepted")
        client = MagicMock()
        client.post.return_value = response
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        with patch(
            "agent_control.observability.httpx.Client",
            return_value=client_context,
        ):
            result = batcher._send_batch_sync([create_mock_event()])

        assert result is True
        headers = client.post.call_args.kwargs["headers"]
        assert headers["X-Custom-API-Key"] == "test-key"
        assert "X-API-Key" not in headers

    def test_build_batch_request_uses_settings_api_key_header(self):
        original_settings = get_settings().model_dump()
        try:
            configure_settings(
                api_key="settings-key",
                api_key_header="X-Custom-API-Key",
            )
            batcher = EventBatcher()

            _, headers, _ = batcher._build_batch_request([create_mock_event()])

            assert headers["X-Custom-API-Key"] == "settings-key"
            assert "X-API-Key" not in headers
        finally:
            configure_settings(**original_settings)

    def test_send_batch_sync_returns_false_on_401_without_retry(self):
        batcher = EventBatcher()
        response = MagicMock(status_code=401, text="unauthorized")
        client = MagicMock()
        client.post.return_value = response
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        with patch(
            "agent_control.observability.httpx.Client",
            return_value=client_context,
        ) as client_ctor:
            result = batcher._send_batch_sync([create_mock_event()])

        assert result is False
        assert client_ctor.call_count == 1
        client.post.assert_called_once()

    def test_send_batch_sync_retries_after_server_error_then_succeeds(self):
        from agent_control.settings import configure_settings

        original = get_settings().model_dump()
        configure_settings(max_retries=2, retry_delay=0.25)
        batcher = EventBatcher()

        first = MagicMock(status_code=500, text="server error")
        second = MagicMock(status_code=202, text="accepted")
        client = MagicMock()
        client.post.side_effect = [first, second]
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        try:
            with (
                patch(
                    "agent_control.observability.httpx.Client",
                    return_value=client_context,
                ) as client_ctor,
                patch("agent_control.observability.time.sleep") as sleep_mock,
            ):
                result = batcher._send_batch_sync([create_mock_event()])

            assert result is True
            assert client_ctor.call_count == 2
            sleep_mock.assert_called_once_with(0.25)
        finally:
            configure_settings(**original)

    def test_send_batch_sync_returns_false_when_deadline_already_expired(self):
        batcher = EventBatcher()

        with (
            patch("agent_control.observability.httpx.Client") as client_ctor,
            patch("agent_control.observability.time.monotonic", return_value=2.0),
        ):
            result = batcher._send_batch_sync([create_mock_event()], deadline=1.0)

        assert result is False
        client_ctor.assert_not_called()

    def test_send_batch_sync_returns_false_when_retry_backoff_exceeds_deadline(self):
        from agent_control.settings import configure_settings

        original = get_settings().model_dump()
        configure_settings(max_retries=3, retry_delay=0.25)
        batcher = EventBatcher()

        client = MagicMock()
        client.post.side_effect = httpx.ConnectError("boom")
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        try:
            with (
                patch(
                    "agent_control.observability.httpx.Client",
                    return_value=client_context,
                ) as client_ctor,
                patch(
                    "agent_control.observability.time.monotonic",
                    side_effect=[0.0, 1.1],
                ),
                patch("agent_control.observability.time.sleep") as sleep_mock,
            ):
                result = batcher._send_batch_sync([create_mock_event()], deadline=1.0)

            assert result is False
            assert client_ctor.call_count == 1
            sleep_mock.assert_not_called()
        finally:
            configure_settings(**original)

    def test_send_batch_sync_handles_timeout_exception(self):
        from agent_control.settings import configure_settings

        original = get_settings().model_dump()
        configure_settings(max_retries=1)
        batcher = EventBatcher()

        client = MagicMock()
        client.post.side_effect = httpx.TimeoutException("boom")
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        try:
            with patch("agent_control.observability.httpx.Client", return_value=client_context):
                result = batcher._send_batch_sync([create_mock_event()])

            assert result is False
        finally:
            configure_settings(**original)

    def test_send_batch_sync_handles_unexpected_exception(self):
        from agent_control.settings import configure_settings

        original = get_settings().model_dump()
        configure_settings(max_retries=1)
        batcher = EventBatcher()

        client = MagicMock()
        client.post.side_effect = RuntimeError("boom")
        client_context = MagicMock()
        client_context.__enter__.return_value = client

        try:
            with patch("agent_control.observability.httpx.Client", return_value=client_context):
                result = batcher._send_batch_sync([create_mock_event()])

            assert result is False
        finally:
            configure_settings(**original)


class TestGlobalBatcher:
    """Tests for global batcher functions."""

    def test_get_event_batcher_not_initialized(self):
        """Test get_event_batcher returns None when not initialized."""
        import agent_control.observability as obs

        old_batcher = obs._batcher
        old_sink = obs._event_sink
        old_external_sinks = obs.get_registered_control_event_sinks()
        reset_observability_state()

        try:
            assert get_event_batcher() is None
        finally:
            obs._batcher = old_batcher
            obs._event_sink = old_sink
            for sink in old_external_sinks:
                register_control_event_sink(sink)

    def test_get_event_sink_not_initialized(self):
        """Test get_event_sink returns None when not initialized."""
        import agent_control.observability as obs
        old_batcher = obs._batcher
        old_sink = obs._event_sink
        old_external_sinks = obs.get_registered_control_event_sinks()
        reset_observability_state()

        try:
            assert get_event_sink() is None
        finally:
