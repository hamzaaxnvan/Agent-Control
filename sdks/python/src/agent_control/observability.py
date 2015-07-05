"""
Event batching and transmission for Agent Control observability.

This module provides:
1. EventBatcher for collecting and sending control execution events to the server
2. Standard library-compliant logging setup for the SDK

Logging:
    The SDK follows Python logging best practices:
    - Uses hierarchical logger names (agent_control.*)
    - Adds only NullHandler (no formatters or handlers)
    - Applications control log configuration via logging.basicConfig() or handlers

    Example - Configure logging in your application:
        import logging
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('agent_control').setLevel(logging.DEBUG)

Event Batching Usage:
    from agent_control.observability import get_event_batcher, add_event

    # Add an event (usually done automatically by @control decorator)
    add_event(event)

    # On shutdown, flush remaining events
    await shutdown_observability()

Configuration (Environment Variables):
    # Server connection
    AGENT_CONTROL_API_KEY_HEADER: API key header name (default: X-API-Key)

    # Observability (event batching)
    AGENT_CONTROL_OBSERVABILITY_ENABLED: Enable observability (default: true)
    AGENT_CONTROL_OBSERVABILITY_SINK_NAME: Selected control-event sink (default: default)
    AGENT_CONTROL_OBSERVABILITY_SINK_CONFIG: JSON config for the selected sink
    AGENT_CONTROL_OTEL_ENABLED: Enable the built-in OTEL sink (default: false)
    AGENT_CONTROL_OTEL_ENDPOINT: OTLP HTTP endpoint for exported control-event spans
    AGENT_CONTROL_OTEL_HEADERS: JSON object of OTLP exporter headers
    AGENT_CONTROL_OTEL_SERVICE_NAME: OTEL service.name for emitted spans
    AGENT_CONTROL_BATCH_SIZE: Max events per batch (default: 100)
    AGENT_CONTROL_FLUSH_INTERVAL: Seconds between flushes (default: 5.0)
    AGENT_CONTROL_SHUTDOWN_JOIN_TIMEOUT: Seconds to wait for worker shutdown (default: 5.0)
    AGENT_CONTROL_SHUTDOWN_FLUSH_TIMEOUT: Seconds to wait for fallback flush (default: 5.0)
    AGENT_CONTROL_SHUTDOWN_MAX_FAILED_FLUSHES: Consecutive failed flushes before stop (default: 1)

    # SDK Logging Behavior (what logs to emit)
    AGENT_CONTROL_LOG_ENABLED: Master switch for SDK logging (default: true)
    AGENT_CONTROL_LOG_LEVEL: Kept for backwards compat; use logging.setLevel() instead
    AGENT_CONTROL_LOG_SPAN_START: Emit span start logs (default: true)
    AGENT_CONTROL_LOG_SPAN_END: Emit span end logs (default: true)
    AGENT_CONTROL_LOG_CONTROL_EVAL: Emit per-control evaluation logs (default: true)
"""

from __future__ import annotations

import asyncio
import atexit
import inspect
import logging
import threading
import time
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
from agent_control_models import JSONObject
from agent_control_telemetry.sink_selection import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
    ControlEventSinkFactory,
    ControlEventSinkFactoryRegistry,
    ControlEventSinkSelection,
    SinkSelectionError,
)
from agent_control_telemetry.sinks import (
    BaseControlEventSink,
    ControlEventSink,
    SinkResult,
)

from agent_control.settings import configure_settings, get_settings

if TYPE_CHECKING:
    from agent_control_models import ControlExecutionEvent
    from opentelemetry.sdk.trace import TracerProvider

from .otel_sink import (
    OTEL_CONTROL_EVENT_SINK_NAME,
    create_otel_control_event_sink,
)

# =============================================================================
# Logger Setup - Standard Library Pattern
# =============================================================================
#
# Following Python logging best practices for libraries:
# - Use hierarchical logger names (agent_control.*)
# - Add only NullHandler to suppress "No handler" warnings
# - Let applications configure handlers, formatters, and levels
# - Provide behavioral settings to control what the SDK logs
#
# Applications should configure agent_control loggers like this:
#   import logging
#   logging.basicConfig(level=logging.INFO)
#   logging.getLogger('agent_control').setLevel(logging.DEBUG)

_ROOT_LOGGER_NAME = "agent_control"


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module under the agent_control namespace.

    This follows standard library conventions - applications control logging
    configuration (handlers, formatters, levels), while the SDK just creates
    properly namespaced loggers.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance under agent_control namespace

    Example:
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    if not name.startswith(_ROOT_LOGGER_NAME):
        name = f"{_ROOT_LOGGER_NAME}.{name}"
    return logging.getLogger(name)


# Add NullHandler to root logger following standard library pattern
# This suppresses "No handlers could be found" warnings while allowing
# applications to configure logging as needed
logging.getLogger(_ROOT_LOGGER_NAME).addHandler(logging.NullHandler())

# Module logger
logger = get_logger(__name__)

# =============================================================================
# Logging Configuration (backwards-compatible wrapper around settings)
# =============================================================================


@dataclass
class LogConfig:
    """
    Configuration for SDK logging behavior.

    This class provides backwards compatibility with the original API.
    Settings are stored in the centralized SDKSettings instance.

    Applications should configure log levels via Python's standard logging
    module (e.g., logging.getLogger('agent_control').setLevel(logging.DEBUG)).
    The fields in this class control which categories of logs the SDK emits.
    """

    enabled: bool = field(default_factory=lambda: get_settings().log_enabled)
    span_start: bool = field(default_factory=lambda: get_settings().log_span_start)
    span_end: bool = field(default_factory=lambda: get_settings().log_span_end)
    control_eval: bool = field(default_factory=lambda: get_settings().log_control_eval)

    @classmethod
    def from_env(cls) -> LogConfig:
        """Load configuration from environment variables (via settings)."""
        return cls(
            enabled=get_settings().log_enabled,
            span_start=get_settings().log_span_start,
            span_end=get_settings().log_span_end,
            control_eval=get_settings().log_control_eval,
        )

    def update(self, config_dict: dict[str, Any]) -> None:
        """Update configuration from a dictionary."""
        # Map old names to new setting names
        mapping = {
            "enabled": "log_enabled",
            "span_start": "log_span_start",
            "span_end": "log_span_end",
            "control_eval": "log_control_eval",
        }
        updates = {}
        for old_key, new_key in mapping.items():
            if old_key in config_dict:
                value = bool(config_dict[old_key])
                updates[new_key] = value
                setattr(self, old_key, value)

        if updates:
            configure_settings(**updates)


# Global logging configuration (for backwards compatibility)
_log_config = LogConfig.from_env()


def configure_logging(config: dict[str, Any] | None = None) -> LogConfig:
    """
    Configure SDK logging behavior (which categories of logs to emit).

    This controls which types of logs the SDK emits, not where they go or
    what level they're logged at. For log level/handler configuration, use
    Python's standard logging module.

    Can be called programmatically to override environment variable defaults.

    Args:
        config: Dictionary with logging options:
            - enabled: bool - Master switch for all SDK logging (default: True)
            - level: str - Kept for backwards compatibility; use logging.setLevel() instead
            - span_start: bool - Emit span start logs (default: True)
            - span_end: bool - Emit span end logs (default: True)
            - control_eval: bool - Emit per-control evaluation logs (default: True)

    Returns:
        Current LogConfig after applying changes

    Example:
        # Control which SDK logs are emitted
        configure_logging({
            "enabled": True,
            "control_eval": False,  # Don't emit per-control logs
        })

        # For log levels, use standard Python logging
        import logging
        logging.getLogger('agent_control').setLevel(logging.DEBUG)
    """
    global _log_config
    if config:
        _log_config.update(config)
    return _log_config


def get_log_config() -> LogConfig:
    """Get the current logging configuration."""
    return _log_config


def _should_log(log_type: str) -> bool:
    """
    Check if a specific log type should be emitted by the SDK.

    This controls which categories of logs the SDK emits, independent of
    Python's logging level filtering. Applications control actual log levels
    via logging.getLogger('agent_control').setLevel().

    Args:
        log_type: Type of log ("span_start", "span_end", "control_eval")

    Returns:
        True if this type of log should be emitted
    """
    if not get_settings().log_enabled:
        return False

    if log_type == "span_start":
        return get_settings().log_span_start
    elif log_type == "span_end":
        return get_settings().log_span_end
    elif log_type == "control_eval":
        return get_settings().log_control_eval

    return True


# =============================================================================
# Event Batching Configuration (now via settings)
# =============================================================================


class EventBatcher:
    """
    Batches control execution events and sends them to the server.

    Events are batched by either:
    - Reaching batch_size events (default: 100)
    - Flush interval timeout (default: 5 seconds)

    Uses a dedicated daemon thread with its own event loop for flush
    scheduling, so it works consistently regardless of caller loop
    lifecycle (sync callers, repeated asyncio.run(), long-lived async
    servers, etc.).

    Thread-safe. add_event() is non-blocking and can be called from
    any thread or async context.

    Attributes:
        server_url: Base URL of the Agent Control server
        api_key: API key for authentication
        api_key_header: HTTP header used to send the API key
        batch_size: Maximum events per batch
        flush_interval: Seconds between automatic flushes
    """

    def __init__(
        self,
        server_url: str | None = None,
        api_key: str | None = None,
        api_key_header: str | None = None,
        batch_size: int | None = None,
        flush_interval: float | None = None,
    ):
        """
        Initialize the EventBatcher.

        Args:
            server_url: Server URL (defaults to get_settings().url)
            api_key: API key (defaults to get_settings().api_key)
            api_key_header: API key header (defaults to get_settings().api_key_header)
            batch_size: Max events per batch (defaults to get_settings().batch_size)
            flush_interval: Seconds between flushes (defaults to get_settings().flush_interval)
        """
        self.server_url = server_url or get_settings().url
        self.api_key = api_key or get_settings().api_key
        self.api_key_header = api_key_header or get_settings().api_key_header
        self.batch_size = batch_size if batch_size is not None else get_settings().batch_size
        if flush_interval is not None:
            self.flush_interval = flush_interval
        else:
            self.flush_interval = get_settings().flush_interval
        self.shutdown_join_timeout = get_settings().shutdown_join_timeout
        self.shutdown_flush_timeout = get_settings().shutdown_flush_timeout
        self.shutdown_max_failed_flushes = get_settings().shutdown_max_failed_flushes

        # Thread-safe event storage
        self._events: list[ControlExecutionEvent] = []
        self._lock = threading.Lock()

        # Dedicated worker loop and thread
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._flush_signal: asyncio.Event | None = None
        self._worker_ready = threading.Event()
        self._graceful_shutdown = False
        self._running = False

        # Reusable HTTP client for connection pooling
        self._client: httpx.AsyncClient | None = None

        # Stats
        self._events_sent = 0
        self._events_dropped = 0
        self._flush_count = 0

    def start(self) -> None:
        """Start the dedicated worker thread and flush loop."""
        if self._running:
            return

        self._running = True
        self._graceful_shutdown = False
        self._worker_ready.clear()
        self._thread = threading.Thread(
            target=self._run_worker_loop,
            name="agent-control-event-batcher",
            daemon=True,
        )
        self._thread.start()
        if not self._worker_ready.wait(timeout=1.0):
            logger.warning("EventBatcher worker thread did not signal readiness in time")
        logger.debug("EventBatcher started (dedicated worker thread)")

    def _run_worker_loop(self) -> None:
        """Entry point for the worker thread. Runs the event loop."""
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._flush_signal = asyncio.Event()
        self._worker_ready.set()
        try:
            loop.run_until_complete(self._flush_loop())
        except RuntimeError:
            # Can happen if emergency stop is requested while loop is running
            pass
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except RuntimeError:
                pass
            loop.close()
            self._flush_signal = None
            self._loop = None
            self._worker_ready.clear()

    def _signal_flush(self) -> None:
        """Wake the worker loop to perform (or finish) a flush cycle."""
        loop = self._loop
        signal = self._flush_signal
        if loop is None or signal is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(signal.set)
        except RuntimeError:
            # Expected during shutdown races: worker teardown can close/swap
            # loop state between our check and call_soon_threadsafe().
            pass

    def _stop_worker(self, *, graceful: bool, join_timeout: float) -> bool:
        """Stop the worker thread and return whether it fully stopped."""
        self._graceful_shutdown = graceful
        self._running = False
        self._signal_flush()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=join_timeout)

        if self._thread and self._thread.is_alive():
            # Emergency fallback if worker is still hung.
            loop = self._loop
            if loop and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass
            self._thread.join(timeout=1.0)

        thread_alive = self._thread.is_alive() if self._thread else False
        if thread_alive:
            logger.warning("EventBatcher worker thread did not stop cleanly")
            return False
        self._thread = None
        return True

    def _build_batch_request(
        self,
        events: list[ControlExecutionEvent],
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Build request components shared by async and sync send paths."""
        url = f"{self.server_url}/api/v1/observability/events"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers[self.api_key_header] = self.api_key
        payload = {"events": [event.model_dump(mode="json") for event in events]}
        return url, headers, payload

    def _send_batch_sync(
        self,
        events: list[ControlExecutionEvent],
        *,
        deadline: float | None = None,
    ) -> bool:
        """Send a batch synchronously for shutdown/atexit fallback."""
        url, headers, payload = self._build_batch_request(events)

        for attempt in range(get_settings().max_retries):
            remaining: float | None = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning("Fallback shutdown flush timed out before sending events")
                    return False

            request_timeout = 30.0
            if remaining is not None:
                request_timeout = max(0.001, min(request_timeout, remaining))

            try:
                with httpx.Client(timeout=request_timeout) as client:
                    response = client.post(url, json=payload, headers=headers)

                if response.status_code == 202:
                    return True
                if response.status_code == 401:
                    logger.error("Authentication failed - check API key")
                    return False

                logger.warning(
                    "Server returned %s during shutdown flush: %s",
                    response.status_code,
                    response.text,
                )
            except httpx.TimeoutException:
                logger.warning("Timeout sending events during shutdown (attempt %d)", attempt + 1)
            except httpx.ConnectError:
                logger.warning(
                    "Connection error sending events during shutdown (attempt %d)",
                    attempt + 1,
                )
            except Exception as e:
                logger.error("Error sending events during shutdown: %s", e)

            if attempt >= get_settings().max_retries - 1:
                break

            retry_delay = get_settings().retry_delay * (attempt + 1)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning("Fallback shutdown flush timed out during retry backoff")
                    return False
                retry_delay = min(retry_delay, remaining)

            if retry_delay > 0:
                time.sleep(retry_delay)

        return False

    def _flush_sync(self, *, deadline: float | None = None) -> bool:
        """Flush a batch synchronously without relying on asyncio state."""
        with self._lock:
            if not self._events:
                return True
            events_to_send = self._events[:self.batch_size]
            self._events = self._events[self.batch_size:]

        success = self._send_batch_sync(events_to_send, deadline=deadline)

        if success:
            with self._lock:
                self._events_sent += len(events_to_send)
                self._flush_count += 1
                total_sent = self._events_sent
            logger.debug(
                f"Flushed {len(events_to_send)} events "
                f"(total sent: {total_sent})"
            )
            return True

        with self._lock:
            self._events = events_to_send + self._events
        logger.warning(f"Failed to send batch, re-queued {len(events_to_send)} events")
        return False

    def _flush_all_without_worker(self, *, timeout: float) -> None:
        """Flush remaining events synchronously when no worker loop is available."""
        deadline = time.monotonic() + max(timeout, 0.0)
        consecutive_failures = 0

        while True:
            with self._lock:
                if not self._events:
                    break

            if time.monotonic() >= deadline:
                logger.warning("Fallback shutdown flush timed out after %.1f seconds", timeout)
                break

            flushed = self._flush_sync(deadline=deadline)
            if flushed:
                consecutive_failures = 0
                continue

            consecutive_failures += 1
            if consecutive_failures >= self.shutdown_max_failed_flushes:
                with self._lock:
                    pending = len(self._events)
                logger.warning(
                    "Stopping sync shutdown flush after %d consecutive failed flushes; "
                    "%d event(s) pending",
                    consecutive_failures,
                    pending,
                )
                break

        # The worker thread normally closes the async client. If shutdown races or
        # interpreter teardown prevented that path from completing, we intentionally
        # do not try to aclose() here because this fallback may be running after
        # asyncio teardown. Drop the reference so shutdown can finish deterministically.
        self._client = None

    def stop(self) -> None:
        """Stop the worker thread. Does not flush remaining events."""
        self._stop_worker(graceful=False, join_timeout=2.0)
        logger.debug("EventBatcher stopped")
