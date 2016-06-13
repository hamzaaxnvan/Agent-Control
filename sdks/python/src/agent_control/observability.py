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
