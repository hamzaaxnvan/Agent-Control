"""Tests for the built-in OpenTelemetry control-event sink."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch

from agent_control import add_event, init_observability, sync_shutdown_observability
from agent_control.observability import is_observability_enabled
from agent_control.otel_sink import (
    OTEL_CONTROL_EVENT_SINK_NAME,
    OTELControlEventSink,
    OTELSDKModules,
    _normalize_attribute_value,
    control_event_to_otel_span,
    create_otel_control_event_sink,
)
from agent_control.settings import configure_settings, get_settings
from agent_control_models import ControlExecutionEvent


def _make_event(**overrides: object) -> ControlExecutionEvent:
    event = ControlExecutionEvent(
        control_execution_id="ce-123",
        trace_id="a" * 32,
        span_id="b" * 16,
        agent_name="test-agent",
        control_id=7,
        control_name="detect-pii",
        check_stage="pre",
        applies_to="llm_call",
        action="observe",
        matched=True,
        confidence=0.85,
        timestamp=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
        execution_duration_ms=12.5,
        evaluator_name="regex",
        selector_path="input",
        error_message=None,
        metadata={
            "labels": ["security", "pii"],
            "threshold": 3,
            "nested": {"k": "v"},
            "selected_data": {"prompt": "raw sensitive input"},
            "selected_data_preview": {
                "type": "dict",
                "value": {"prompt": "raw sensitive input"},
                "truncated": False,
            },
            "engine_selected_data": {"prompt": "raw sensitive input"},
            "engine_selected_data_preview": {
                "type": "dict",
                "value": {"prompt": "raw sensitive input"},
                "truncated": False,
            },
        },
    )
    return event.model_copy(update=overrides)


class FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.end_time: int | None = None
        self.exceptions: list[str] = []
        self.status: FakeStatus | None = None

    def set_attributes(self, attributes: dict[str, object]) -> None:
        self.attributes = dict(attributes)

    def record_exception(self, exc: BaseException) -> None:
        self.exceptions.append(str(exc))

    def set_status(self, status: FakeStatus) -> None:
        self.status = status

    def end(self, end_time: int) -> None:
        self.end_time = end_time


class FakeTracer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.spans: list[FakeSpan] = []
        self.raise_on_start = False

    def start_span(
        self,
        name: str,
        *,
        context: object = None,
        kind: object = None,
        start_time: int | None = None,
    ) -> FakeSpan:
        if self.raise_on_start:
            raise RuntimeError("span creation failed")
        self.calls.append(
            {
                "name": name,
                "context": context,
                "kind": kind,
                "start_time": start_time,
            }
        )
        span = FakeSpan()
        self.spans.append(span)
        return span


class FakeTracerProvider:
    def __init__(self, *, resource: object = None) -> None:
        self.resource = resource
        self.processors: list[object] = []
        self.tracer = FakeTracer()
        self.force_flush_calls = 0
        self.shutdown_calls = 0
        self.tracer_scope_name: str | None = None

    def add_span_processor(self, processor: object) -> None:
        self.processors.append(processor)

    def get_tracer(self, name: str) -> FakeTracer:
        self.tracer_scope_name = name
        return self.tracer

    def force_flush(self) -> None:
        self.force_flush_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeResource:
    @staticmethod
    def create(attributes: dict[str, object]) -> dict[str, object]:
        return {"attributes": attributes}


class FakeBatchSpanProcessor:
    def __init__(self, exporter: object) -> None:
        self.exporter = exporter


class FakeOTLPSpanExporter:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeSpanContext:
    def __init__(
        self,
        *,
        trace_id: int,
        span_id: int,
        is_remote: bool,
        trace_flags: object,
        trace_state: object,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.is_remote = is_remote
        self.trace_flags = trace_flags
        self.trace_state = trace_state


class FakeNonRecordingSpan:
    def __init__(self, span_context: FakeSpanContext) -> None:
        self.span_context = span_context


class FakeTraceFlags(int):
    SAMPLED = 1


class FakeTraceState:
    pass


class FakeStatusCode:
    ERROR = "error"


class FakeStatus:
    def __init__(self, status_code: object, description: str | None = None) -> None:
        self.status_code = status_code
        self.description = description


class FakeSpanKind:
    INTERNAL = "internal"


def _fake_set_span_in_context(span: FakeNonRecordingSpan) -> dict[str, object]:
    return {"parent": span}


def _fake_otel_sdk_modules(global_provider: object = None) -> OTELSDKModules:
    return OTELSDKModules(
        tracer_provider_cls=FakeTracerProvider,
        resource_cls=FakeResource,
        batch_span_processor_cls=FakeBatchSpanProcessor,
        otlp_span_exporter_cls=FakeOTLPSpanExporter,
        span_context_cls=FakeSpanContext,
        non_recording_span_cls=FakeNonRecordingSpan,
        trace_flags_cls=FakeTraceFlags,
        trace_state_cls=FakeTraceState,
        status_cls=FakeStatus,
        status_code_cls=FakeStatusCode,
        span_kind=FakeSpanKind,
        set_span_in_context=_fake_set_span_in_context,
        get_tracer_provider=lambda: global_provider,
    )


def setup_function() -> None:
    original_settings = get_settings().model_dump()
    setup_function.original_settings = original_settings  # type: ignore[attr-defined]
    configure_settings(
        observability_enabled=True,
        observability_sink_name="default",
        observability_sink_config={},
        otel_enabled=False,
        otel_endpoint=None,
        otel_headers={},
        otel_service_name="agent-control-sdk",
    )
    os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)


def teardown_function() -> None:
    sync_shutdown_observability()
    configure_settings(**setup_function.original_settings)  # type: ignore[attr-defined]


def test_control_event_to_otel_span_maps_event_fields() -> None:
    event = _make_event(error_message="blocked")

    span = control_event_to_otel_span(event)

    assert span.trace_id == event.trace_id
    assert span.parent_span_id == event.span_id
    assert span.name == "agent_control.control_execution"
    assert span.attributes["agent_control.control_name"] == "detect-pii"
    assert span.attributes["agent_control.matched"] is True
    assert span.attributes["agent_control.metadata.labels"] == ["security", "pii"]
    assert span.attributes["agent_control.metadata.nested"] == '{"k": "v"}'
    assert "agent_control.metadata.selected_data" not in span.attributes
    assert "agent_control.metadata.selected_data_preview" not in span.attributes
    assert "agent_control.metadata.engine_selected_data" not in span.attributes
    assert "agent_control.metadata.engine_selected_data_preview" not in span.attributes
    assert span.error_message == "blocked"
    assert span.end_time_unix_nano >= span.start_time_unix_nano


def test_control_event_to_otel_span_handles_optional_fields_and_attribute_types() -> None:
    # Given: an event without optional timing or evaluator fields and typed metadata lists
    event = _make_event(
        execution_duration_ms=None,
        evaluator_name=None,
        selector_path=None,
        metadata={
            "bools": [True, False],
            "ints": [1, 2],
            "floats": [1.5, 2.5],
        },
    )

    # When: normalizing it into an OTEL span
    span = control_event_to_otel_span(event)

    # Then: timestamps collapse to an instant and list element types are retained
    assert span.start_time_unix_nano == span.end_time_unix_nano
    assert span.attributes["agent_control.metadata.bools"] == [True, False]
    assert span.attributes["agent_control.metadata.ints"] == [1, 2]
    assert span.attributes["agent_control.metadata.floats"] == [1.5, 2.5]
    assert "agent_control.execution_duration_ms" not in span.attributes
    assert "agent_control.evaluator_name" not in span.attributes
    assert "agent_control.selector_path" not in span.attributes


def test_attribute_normalization_accepts_tuples() -> None:
    # Given: a tuple from an internal event metadata boundary
    value = ("security", "pii")

    # When: normalizing the attribute value directly to reach the tuple-only branch
    normalized = _normalize_attribute_value(value)

    # Then: OTEL receives its supported homogeneous list representation
    assert normalized == ["security", "pii"]


def test_create_otel_control_event_sink_is_inert_when_disabled() -> None:
    configure_settings(otel_enabled=False)

    sink = create_otel_control_event_sink({})
    result = sink.write_events([_make_event()])

    assert sink.is_active() is False
    assert result.accepted == 1
    assert result.dropped == 0


def test_create_otel_control_event_sink_is_inert_without_core_otel_sdk() -> None:
    # Given: an enabled OTEL sink without the optional core SDK dependency
    configure_settings(otel_enabled=True)

    # When: creating the sink
    with patch(
        "agent_control.otel_sink._load_otel_sdk_modules",
        side_effect=ImportError("opentelemetry-sdk is unavailable"),
    ):
        sink = create_otel_control_event_sink({})

    # Then: events are safely accepted by an inactive no-op sink
    assert sink.is_active() is False
    assert sink.write_events([_make_event()]).accepted == 1


def test_create_otel_control_event_sink_is_inert_without_owned_pipeline_exporter() -> None:
    # Given: core OTEL support but no reusable provider or OTLP/HTTP exporter
    configure_settings(
        otel_enabled=True,
        otel_endpoint="http://collector:4318/v1/traces",
    )
    sdk_modules = replace(_fake_otel_sdk_modules(), otlp_span_exporter_cls=None)

    # When: Agent Control attempts to create its owned pipeline
    with patch(
        "agent_control.otel_sink._load_otel_sdk_modules",
        return_value=sdk_modules,
    ), patch(
        "agent_control.otel_sink._load_otlp_span_exporter_cls",
        side_effect=ImportError("OTLP exporter is unavailable"),
    ):
        sink = create_otel_control_event_sink({})

    # Then: it falls back to the inactive no-op sink
    assert sink.is_active() is False


def test_create_otel_control_event_sink_without_exporter_stays_inert() -> None:
    configure_settings(otel_enabled=True, otel_endpoint=None)

    with patch(
        "agent_control.otel_sink._load_otel_sdk_modules",
        return_value=_fake_otel_sdk_modules(),
    ):
        sink = create_otel_control_event_sink({})

    assert sink.is_active() is False


def test_create_otel_control_event_sink_uses_exporter_config_and_emits_spans() -> None:
    configure_settings(
        otel_enabled=True,
        otel_endpoint="http://collector:4318/v1/traces",
        otel_headers={"x-api-key": "secret"},
        otel_service_name="agent-control-tests",
    )

    with patch(
        "agent_control.otel_sink._load_otel_sdk_modules",
