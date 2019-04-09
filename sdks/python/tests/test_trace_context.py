"""Tests for the telemetry trace context provider interface."""

from agent_control_telemetry.trace_context import (
    clear_trace_context_provider,
    get_trace_context_from_provider,
    set_trace_context_provider,
)


def teardown_function() -> None:
    clear_trace_context_provider()


def test_get_trace_context_from_provider_returns_registered_context() -> None:
    set_trace_context_provider(
        lambda: {
            "trace_id": "a" * 32,
            "span_id": "b" * 16,
        }
    )

    assert get_trace_context_from_provider() == {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
    }
