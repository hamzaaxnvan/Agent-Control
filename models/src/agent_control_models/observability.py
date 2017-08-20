"""Observability models for tracking control executions.

This module provides models for:
- Control execution events (what controls ran, with what results)
- Batch event ingestion (SDK -> Server)
- Event queries (filtering and pagination)
- Aggregated statistics (pre-computed metrics)
- Real-time streaming updates
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator

from .actions import (
    ActionDecision,
    normalize_action,
    validate_action_list,
)
from .agent import AGENT_NAME_MIN_LENGTH, AGENT_NAME_PATTERN, normalize_agent_name
from .base import BaseModel

# =============================================================================
# Core Event Model
# =============================================================================


class ControlExecutionEvent(BaseModel):
    """
    Represents a single control execution event.

    This is the core observability data model, capturing:
    - Identity: control_execution_id, trace_id, span_id (OpenTelemetry-compatible)
    - Context: agent, control, check stage, applies to
    - Result: action taken, whether matched, confidence score
    - Timing: when it happened, how long it took
    - Optional details: evaluator name, selector path, errors, metadata

    Attributes:
        control_execution_id: Unique ID for this specific control execution
        trace_id: OpenTelemetry-compatible trace ID (128-bit hex, 32 chars)
        span_id: OpenTelemetry-compatible span ID (64-bit hex, 16 chars)
        agent_name: Identifier of the agent that executed the control
        control_id: Database ID of the control
        control_name: Name of the control (denormalized for queries)
        check_stage: "pre" (before execution) or "post" (after execution)
        applies_to: "llm_call", "tool_call", or a custom step type with a "_call" suffix
        action: The action taken (deny, steer, observe)
        matched: Whether the control evaluator matched
        confidence: Confidence score from the evaluator (0.0-1.0)
        timestamp: When the control was executed (UTC)
        execution_duration_ms: How long the control evaluation took
        evaluator_name: Name of the evaluator used
        selector_path: The selector path used to extract data
        error_message: Error message if evaluation failed
        metadata: Additional metadata for extensibility
    """

    # Unique identifiers (OpenTelemetry-compatible)
    control_execution_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID for this control execution",
    )
    trace_id: str = Field(
        ...,
        min_length=1,
        description="Trace ID for distributed tracing (SDK generates OTEL-compatible 32-char hex)",
    )
    span_id: str = Field(
        ...,
        min_length=1,
        description="Span ID for distributed tracing (SDK generates OTEL-compatible 16-char hex)",
    )

    # Agent identity
    agent_name: str = Field(
        ...,
        min_length=AGENT_NAME_MIN_LENGTH,
        pattern=AGENT_NAME_PATTERN,
        description="Identifier of the agent",
    )

    # Control info
    control_id: int = Field(..., description="Database ID of the control")
    control_name: str = Field(..., description="Name of the control (denormalized)")

    # Execution context
    check_stage: Literal["pre", "post"] = Field(
        ..., description="Check stage: 'pre' or 'post'"
    )
    applies_to: str = Field(
        ...,
        min_length=1,
        description="Type of call or custom step type with a '_call' suffix",
    )

    # Result
    action: ActionDecision = Field(
        ..., description="Action taken by the control"
    )
    matched: bool = Field(
        ..., description="Whether the evaluator matched (True) or not (False)"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)"
    )

    # Timing
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the control was executed (UTC)",
    )
    execution_duration_ms: float | None = Field(
        default=None, ge=0, description="Execution duration in milliseconds"
    )

    # Optional details
    evaluator_name: str | None = Field(
        default=None, description="Name of the evaluator used"
    )
    selector_path: str | None = Field(
        default=None, description="Selector path used to extract data"
    )
    error_message: str | None = Field(
        default=None, description="Error message if evaluation failed"
    )

    # Extensibility
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, v: str) -> str:
        """
        Validate trace_id is non-empty.

        We use lenient validation to support different tracing backends
        (OTEL, X-Ray, Jaeger, etc.) and user-provided trace IDs.
        The SDK generates OTEL-compatible IDs (32-char hex), but we accept
        any non-empty string for flexibility.
        """
        if not v or not v.strip():
            raise ValueError("trace_id cannot be empty")
        return v

    @field_validator("span_id")
    @classmethod
    def validate_span_id(cls, v: str) -> str:
        """
        Validate span_id is non-empty.

        We use lenient validation to support different tracing backends
        (OTEL, X-Ray, Jaeger, etc.) and user-provided span IDs.
        The SDK generates OTEL-compatible IDs (16-char hex), but we accept
        any non-empty string for flexibility.
        """
        if not v or not v.strip():
            raise ValueError("span_id cannot be empty")
        return v

    @field_validator("agent_name", mode="before")
    @classmethod
    def validate_and_normalize_agent_name(cls, value: str) -> str:
        return normalize_agent_name(str(value))

    @field_validator("action", mode="before")
    @classmethod
    def normalize_event_action(cls, value: str) -> ActionDecision:
        return normalize_action(value)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "control_execution_id": "550e8400-e29b-41d4-a716-446655440000",
                    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                    "span_id": "00f067aa0ba902b7",
                    "agent_name": "my-agent",
                    "control_id": 123,
                    "control_name": "sql-injection-check",
                    "check_stage": "pre",
                    "applies_to": "llm_call",
                    "action": "deny",
                    "matched": True,
                    "confidence": 0.95,
                    "timestamp": "2025-01-09T10:30:00Z",
                    "execution_duration_ms": 15.3,
                    "evaluator_name": "regex",
                    "selector_path": "input",
                }
            ]
        }
    }


# =============================================================================
# Batch Ingestion Models
# =============================================================================


class BatchEventsRequest(BaseModel):
    """
    Request model for batch event ingestion.

    SDKs batch events and send them to the server periodically.
    This reduces HTTP overhead significantly (100x reduction).

    Attributes:
        events: List of control execution events to ingest
    """

    events: list[ControlExecutionEvent] = Field(
        ..., min_length=1, max_length=1000, description="List of events to ingest"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "events": [
                        {
                            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                            "span_id": "00f067aa0ba902b7",
                            "agent_name": "my-agent",
                            "control_id": 123,
                            "control_name": "sql-injection-check",
                            "check_stage": "pre",
                            "applies_to": "llm_call",
                            "action": "deny",
                            "matched": True,
                            "confidence": 0.95,
                        }
                    ]
                }
            ]
        }
    }


class BatchEventsResponse(BaseModel):
    """
    Response model for batch event ingestion.

    Attributes:
        received: Number of events received
        enqueued: Number of events successfully enqueued
        dropped: Number of events dropped (queue full)
        status: Overall status ('queued', 'partial', 'failed')
    """

    received: int = Field(..., ge=0, description="Number of events received")
    enqueued: int = Field(..., ge=0, description="Number of events enqueued")
    dropped: int = Field(..., ge=0, description="Number of events dropped")
    status: Literal["queued", "partial", "failed"] = Field(
        ..., description="Overall ingestion status"
    )


# =============================================================================
# Query Models
# =============================================================================


class EventQueryRequest(BaseModel):
    """
    Request model for querying raw events.

    Supports filtering by various criteria and pagination.

    Attributes:
        trace_id: Filter by trace ID (get all events for a request)
        span_id: Filter by span ID (get all events for a function call)
        control_execution_id: Filter by specific event ID
        agent_name: Filter by agent identifier
        control_ids: Filter by control IDs
        actions: Filter by actions (deny, steer, observe)
        matched: Filter by matched status
        check_stages: Filter by check stages (pre, post)
        applies_to: Filter by call type or custom call type
        start_time: Filter events after this time
        end_time: Filter events before this time
        limit: Maximum number of events to return
        offset: Offset for pagination
    """

    trace_id: str | None = Field(
        default=None, description="Filter by trace ID (all events for a request)"
    )
