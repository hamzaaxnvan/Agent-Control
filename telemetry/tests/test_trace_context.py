"""Tests for the telemetry trace context provider contract."""

from typing import Any

import pytest

from agent_control_telemetry.trace_context import (
    clear_trace_context_provider,
    get_trace_context_from_provider,
    set_trace_context_provider,
)


def teardown_function() -> None:
    clear_trace_context_provider()


def test_get_trace_context_from_provider_returns_registered_context() -> None:
    # Given: a provider that returns valid trace and span identifiers
    set_trace_context_provider(
        lambda: {
            "trace_id": "trace-123",
            "span_id": "span-456",
        }
    )

    # When: reading the current trace context
    trace_context = get_trace_context_from_provider()

    # Then: the provider values are returned unchanged
