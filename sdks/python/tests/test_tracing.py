"""Tests for the tracing module."""

import pytest

from agent_control_telemetry.trace_context import (
    clear_trace_context_provider,
    set_trace_context_provider,
)
from agent_control.tracing import (
    _generate_span_id,
    _generate_trace_id,
    get_current_span_id,
    get_current_trace_id,
    get_trace_and_span_ids,
    is_otel_available,
    reset_trace_context,
    set_trace_context,
    validate_span_id,
    validate_trace_id,
    with_trace,
)


def teardown_function() -> None:
    clear_trace_context_provider()


class TestIdGeneration:
    """Tests for trace and span ID generation."""

    def test_generate_trace_id_format(self):
        """Test that generated trace IDs are OTEL-compatible (32 hex chars)."""
        trace_id = _generate_trace_id()
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_generate_trace_id_unique(self):
        """Test that generated trace IDs are unique."""
        ids = {_generate_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_generate_span_id_format(self):
        """Test that generated span IDs are OTEL-compatible (16 hex chars)."""
        span_id = _generate_span_id()
        assert len(span_id) == 16
        assert all(c in "0123456789abcdef" for c in span_id)

    def test_generate_span_id_unique(self):
        """Test that generated span IDs are unique."""
        ids = {_generate_span_id() for _ in range(100)}
        assert len(ids) == 100


class TestIdValidation:
    """Tests for trace and span ID validation."""

    def test_validate_trace_id_valid(self):
        """Test validation of valid trace IDs."""
        assert validate_trace_id("a" * 32) is True
        assert validate_trace_id("0" * 32) is True
        assert validate_trace_id("f" * 32) is True
        assert validate_trace_id("4bf92f3577b34da6a3ce929d0e0e4736") is True

    def test_validate_trace_id_invalid_length(self):
        """Test validation rejects wrong-length trace IDs."""
        assert validate_trace_id("a" * 31) is False
        assert validate_trace_id("a" * 33) is False
        assert validate_trace_id("") is False

    def test_validate_trace_id_invalid_chars(self):
        """Test validation rejects non-hex characters."""
        assert validate_trace_id("g" * 32) is False
        assert validate_trace_id("a" * 31 + "G") is False

    def test_validate_trace_id_invalid_type(self):
        """Test validation rejects non-string types."""
        assert validate_trace_id(12345) is False  # type: ignore
        assert validate_trace_id(None) is False  # type: ignore

    def test_validate_span_id_valid(self):
        """Test validation of valid span IDs."""
        assert validate_span_id("a" * 16) is True
        assert validate_span_id("0" * 16) is True
        assert validate_span_id("f" * 16) is True
        assert validate_span_id("00f067aa0ba902b7") is True

    def test_validate_span_id_invalid_length(self):
        """Test validation rejects wrong-length span IDs."""
        assert validate_span_id("a" * 15) is False
        assert validate_span_id("a" * 17) is False
        assert validate_span_id("") is False

    def test_validate_span_id_invalid_chars(self):
        """Test validation rejects non-hex characters."""
        assert validate_span_id("g" * 16) is False

    def test_validate_span_id_invalid_type(self):
        """Test validation rejects non-string types."""
        assert validate_span_id(12345) is False  # type: ignore
        assert validate_span_id(None) is False  # type: ignore


class TestContextVariables:
    """Tests for trace context variable management."""

    def test_set_and_get_trace_context(self):
        """Test setting and getting trace context."""
        trace_id = "a" * 32
        span_id = "b" * 16

        trace_token, span_token = set_trace_context(trace_id, span_id)
        try:
            assert get_current_trace_id() == trace_id
            assert get_current_span_id() == span_id
        finally:
            reset_trace_context(trace_token, span_token)

    def test_reset_trace_context(self):
        """Test that resetting context restores previous values."""
        # First, ensure no context is set
        original_trace = get_current_trace_id()
        original_span = get_current_span_id()

        # Set new context
        trace_token, span_token = set_trace_context("a" * 32, "b" * 16)

        # Reset context
        reset_trace_context(trace_token, span_token)

        # Verify original values are restored
        assert get_current_trace_id() == original_trace
        assert get_current_span_id() == original_span

    def test_get_current_ids_without_context(self):
        """Test getting current IDs when no context is set."""
        # These may return None or OTEL context if available
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()
        # Just verify they don't raise
        assert trace_id is None or isinstance(trace_id, str)
        assert span_id is None or isinstance(span_id, str)

    def test_get_current_trace_id_uses_provider(self):
        """Test that get_current_trace_id uses external provider before OTEL fallback."""
        expected_trace = "a" * 32
        set_trace_context_provider(
            lambda: {
                "trace_id": expected_trace,
