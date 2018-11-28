"""Tests for telemetry sink contracts."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

from agent_control_models import ControlExecutionEvent

from agent_control_telemetry import (
    BaseAsyncControlEventSink,
    BaseControlEventSink,
    SinkResult,
)


def _make_event(*, control_id: int) -> ControlExecutionEvent:
    return ControlExecutionEvent(
        trace_id="trace-123",
        span_id="span-456",
        agent_name="demo-agent",
        control_id=control_id,
        control_name=f"control-{control_id}",
        check_stage="pre",
        applies_to="tool_call",
