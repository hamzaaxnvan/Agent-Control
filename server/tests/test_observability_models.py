"""Tests for observability Pydantic and SQLAlchemy models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_control_models import (
    BatchEventsRequest,
    BatchEventsResponse,
    ControlExecutionEvent,
    ControlStats,
    EventQueryRequest,
    EventQueryResponse,
    StatsRequest,
    StatsResponse,
)


class TestControlExecutionEvent:
    """Tests for ControlExecutionEvent model."""

    def test_valid_event(self):
        """Test creating a valid event."""
        event = ControlExecutionEvent(
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            span_id="00f067aa0ba902b7",
                agent_name="test-agent",
            control_id=123,
            control_name="sql-injection-check",
            check_stage="pre",
            applies_to="llm_call",
            action="deny",
            matched=True,
            confidence=0.95,
        )
        assert event.matched is True
        assert event.confidence == 0.95
        assert len(event.trace_id) == 32
        assert len(event.span_id) == 16
        # control_execution_id should be auto-generated
        assert event.control_execution_id is not None

    def test_trace_id_validation_empty(self):
        """Test that trace_id cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            ControlExecutionEvent(
                trace_id="",
                span_id="00f067aa0ba902b7",
                agent_name="test-agent",
                control_id=123,
                control_name="test",
                check_stage="pre",
                applies_to="llm_call",
                action="observe",
                matched=False,
                confidence=0.5,
            )
        assert "trace_id" in str(exc_info.value)

    def test_trace_id_accepts_various_formats(self):
        """Test that trace_id accepts various formats for flexibility."""
        # Should accept non-standard formats to support different tracing backends
        event = ControlExecutionEvent(
            trace_id="my-custom-trace-id",  # non-hex, non-32-char
            span_id="my-span",
                agent_name="test-agent",
            control_id=123,
            control_name="test",
            check_stage="pre",
            applies_to="llm_call",
            action="observe",
            matched=False,
            confidence=0.5,
        )
        assert event.trace_id == "my-custom-trace-id"
        assert event.span_id == "my-span"

    def test_span_id_validation_empty(self):
        """Test that span_id cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            ControlExecutionEvent(
                trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
                span_id="",
                agent_name="test-agent",
                control_id=123,
                control_name="test",
                check_stage="pre",
                applies_to="llm_call",
                action="observe",
                matched=False,
                confidence=0.5,
            )
        assert "span_id" in str(exc_info.value)

    def test_confidence_bounds(self):
        """Test that confidence must be between 0 and 1."""
        with pytest.raises(ValidationError):
            ControlExecutionEvent(
                trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
                span_id="00f067aa0ba902b7",
                agent_name="test-agent",
                control_id=123,
                control_name="test",
                check_stage="pre",
                applies_to="llm_call",
                action="observe",
                matched=False,
                confidence=1.5,  # > 1.0
            )

    def test_check_stage_values(self):
        """Test that check_stage must be 'pre' or 'post'."""
        with pytest.raises(ValidationError):
            ControlExecutionEvent(
                trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
                span_id="00f067aa0ba902b7",
                agent_name="test-agent",
                control_id=123,
                control_name="test",
                check_stage="invalid",  # invalid
                applies_to="llm_call",
                action="observe",
                matched=False,
                confidence=0.5,
            )

    def test_action_values(self):
        """Test canonical actions and legacy advisory normalization."""
        expected_actions = {
            "allow": "observe",
            "deny": "deny",
            "steer": "steer",
            "warn": "observe",
            "log": "observe",
            "observe": "observe",
        }
        for action, expected in expected_actions.items():
            event = ControlExecutionEvent(
                trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
                span_id="00f067aa0ba902b7",
                agent_name="test-agent",
                control_id=123,
                control_name="test",
                check_stage="pre",
                applies_to="llm_call",
                action=action,
                matched=True,
                confidence=0.9,
