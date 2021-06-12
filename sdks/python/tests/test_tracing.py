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

