"""Per-control duration survives SDK response parsing and event reconstruction."""

from collections.abc import Iterator, Sequence
from functools import partial
from typing import Any, Literal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from agent_control_models import ControlExecutionEvent, Step
from agent_control_telemetry import REGISTERED_CONTROL_EVENT_SINK_NAME
from agent_control_telemetry.sinks import BaseControlEventSink, SinkResult

from agent_control import (
    AgentControlClient,
    control,
    register_control_event_sink,
    unregister_control_event_sink,
)
from agent_control._state import state
from agent_control.evaluation import check_evaluation, check_evaluation_with_local
from agent_control.otel_sink import control_event_to_otel_span
from agent_control.settings import configure_settings, get_settings

ResultCategory = Literal["matches", "errors", "non_matches"]


class RecordingSink(BaseControlEventSink):
    """Capture the events delivered through the public sink API."""

    def __init__(self) -> None:
        self.events: list[ControlExecutionEvent] = []

    def write_events(self, events: Sequence[ControlExecutionEvent]) -> SinkResult:
        self.events.extend(events)
        return SinkResult(accepted=len(events), dropped=0)


@pytest.fixture
def recording_sink(monkeypatch: pytest.MonkeyPatch) -> Iterator[RecordingSink]:
    # Given: an isolated SDK session exporting to a registered event sink.
    previous_settings = get_settings().model_dump()
    for name in ("current_agent", "target_type", "target_id", "server_controls"):
        monkeypatch.setattr(state, name, None)
    sink = RecordingSink()
    register_control_event_sink(sink)
    configure_settings(
        observability_enabled=True,
        observability_sink_name=REGISTERED_CONTROL_EVENT_SINK_NAME,
    )
    try:
        yield sink
    finally:
        unregister_control_event_sink(sink)
        configure_settings(**previous_settings)


def _server_response(category: ResultCategory, duration: float | None) -> dict[str, Any]:
    match: dict[str, Any] = {
        "control_id": 2,
        "control_name": "server-control",
        "control_execution_id": "server-execution",
        "action": "observe",
        "result": {
            "matched": category == "matches",
