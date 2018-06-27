"""OpenTelemetry sink support for Agent Control control-execution events."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from agent_control_models import ControlExecutionEvent, JSONObject
from agent_control_telemetry.sinks import BaseControlEventSink, SinkResult

from .settings import get_settings
from .tracing import _generate_span_id, validate_span_id, validate_trace_id

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)

OTEL_CONTROL_EVENT_SINK_NAME = "otel"
_OTEL_INSTRUMENTATION_SCOPE = "agent_control.observability"
_OTEL_NOOP_WARNING = (
    "OpenTelemetry sink selected but OpenTelemetry SDK/exporter dependencies are not available; "
    "control events will be accepted without being exported"
)
_OTEL_EXPORTER_MISSING_WARNING = (
    "OpenTelemetry sink selected but no OTLP exporter configuration was found; "
    "control events will not be exported"
)
_DEBUG_METADATA_ATTRIBUTE_KEYS = frozenset(
    {
        "selected_data",
        "selected_data_preview",
        "engine_selected_data",
        "engine_selected_data_preview",
    }
)

AttributeValue = str | bool | int | float | list[str] | list[bool] | list[int] | list[float]


@dataclass(frozen=True)
class OTELControlEventSpan:
    """Normalized OTEL span payload derived from a control event."""

    name: str
    trace_id: str
    parent_span_id: str
    attributes: dict[str, AttributeValue]
    start_time_unix_nano: int
    end_time_unix_nano: int
    error_message: str | None = None


@dataclass(frozen=True)
class OTELSinkConfig:
    """Configuration for OTEL sink creation."""

    enabled: bool
    endpoint: str | None
    headers: dict[str, str]
    service_name: str


@dataclass(frozen=True)
class OTELSDKModules:
    """References to the OTEL SDK classes/functions used by the sink."""

    tracer_provider_cls: type[Any]
    resource_cls: type[Any]
    batch_span_processor_cls: type[Any]
    otlp_span_exporter_cls: type[Any] | None
    span_context_cls: type[Any]
    non_recording_span_cls: type[Any]
    trace_flags_cls: type[Any]
    trace_state_cls: type[Any]
    status_cls: type[Any]
    status_code_cls: type[Any]
    span_kind: Any
    set_span_in_context: Any
    get_tracer_provider: Any


def _to_unix_nano(timestamp: datetime, /) -> int:
    return int(timestamp.astimezone(UTC).timestamp() * 1_000_000_000)


def _normalize_attribute_value(value: object) -> AttributeValue:
    """Coerce arbitrary metadata into a value OTEL span attributes accept."""
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        if all(isinstance(item, bool) for item in value):
            return [item for item in value]
        if all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return [item for item in value]
        if all(isinstance(item, float) for item in value):
            return [item for item in value]
        if all(isinstance(item, str) for item in value):
            return [item for item in value]
    if isinstance(value, tuple):
        return _normalize_attribute_value(list(value))
    return json.dumps(value, default=str, sort_keys=True)


def control_event_to_otel_span(event: ControlExecutionEvent) -> OTELControlEventSpan:
    """Convert a control-execution event into OTEL span data."""
    end_time_unix_nano = _to_unix_nano(event.timestamp)
    if event.execution_duration_ms is not None:
        start_time_unix_nano = max(
            0,
            end_time_unix_nano - int(event.execution_duration_ms * 1_000_000),
        )
    else:
        start_time_unix_nano = end_time_unix_nano

    attributes: dict[str, AttributeValue] = {
        "agent_control.control_execution_id": event.control_execution_id,
        "agent_control.agent_name": event.agent_name,
        "agent_control.control_id": event.control_id,
        "agent_control.control_name": event.control_name,
        "agent_control.check_stage": event.check_stage,
        "agent_control.applies_to": event.applies_to,
        "agent_control.action": event.action,
        "agent_control.matched": event.matched,
        "agent_control.confidence": event.confidence,
        "agent_control.event_timestamp": event.timestamp.isoformat(),
    }

    if event.execution_duration_ms is not None:
        attributes["agent_control.execution_duration_ms"] = event.execution_duration_ms
    if event.evaluator_name is not None:
        attributes["agent_control.evaluator_name"] = event.evaluator_name
    if event.selector_path is not None:
        attributes["agent_control.selector_path"] = event.selector_path
    if event.error_message is not None:
        attributes["agent_control.error_message"] = event.error_message

    for key, value in sorted(event.metadata.items()):
        if key in _DEBUG_METADATA_ATTRIBUTE_KEYS:
            continue
        attributes[f"agent_control.metadata.{key}"] = _normalize_attribute_value(value)

    return OTELControlEventSpan(
        name="agent_control.control_execution",
        trace_id=event.trace_id,
        parent_span_id=event.span_id,
        attributes=attributes,
        start_time_unix_nano=start_time_unix_nano,
        end_time_unix_nano=end_time_unix_nano,
        error_message=event.error_message,
    )


class _NoOpControlEventSink(BaseControlEventSink):
    """Sink that accepts events but intentionally emits nothing."""

    def is_active(self) -> bool:
        return False

    def write_events(self, events: Sequence[ControlExecutionEvent]) -> SinkResult:
        return SinkResult(accepted=len(events), dropped=0)


class OTELControlEventSink(BaseControlEventSink):
    """Emit control-execution events as OpenTelemetry spans."""

    def __init__(
        self,
        *,
        tracer_provider: Any,
        tracer: Any,
        sdk_modules: OTELSDKModules,
        provider_owned: bool,
    ) -> None:
        self._tracer_provider: Any = tracer_provider
        self._tracer: Any = tracer
        self._sdk_modules = sdk_modules
        self._provider_owned = provider_owned

    def write_events(self, events: Sequence[ControlExecutionEvent]) -> SinkResult:
        accepted = 0
        dropped = 0

        for event in events:
            try:
                self._write_event(event)
                accepted += 1
            except Exception:
                logger.warning("Failed to emit control event to OTEL", exc_info=True)
                dropped += 1

        return SinkResult(accepted=accepted, dropped=dropped)

    def flush(self) -> None:
        force_flush = getattr(self._tracer_provider, "force_flush", None)
        if callable(force_flush):
            force_flush()

    def close(self) -> None:
        if not self._provider_owned:
            return
        shutdown = getattr(self._tracer_provider, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def _write_event(self, event: ControlExecutionEvent) -> None:
        span_data = control_event_to_otel_span(event)
        parent_context = self._build_parent_context(span_data)
        span = self._tracer.start_span(
            span_data.name,
            context=parent_context,
            kind=self._sdk_modules.span_kind.INTERNAL,
            start_time=span_data.start_time_unix_nano,
        )
        span.set_attributes(span_data.attributes)
        if span_data.error_message:
            record_exception = getattr(span, "record_exception", None)
            if callable(record_exception):
                record_exception(RuntimeError(span_data.error_message))
            set_status = getattr(span, "set_status", None)
            if callable(set_status):
                set_status(
                    self._sdk_modules.status_cls(
                        self._sdk_modules.status_code_cls.ERROR,
                        span_data.error_message,
                    )
                )
        span.end(end_time=span_data.end_time_unix_nano)

    def _build_parent_context(self, span_data: OTELControlEventSpan) -> object | None:
        trace_id = span_data.trace_id
        parent_span_id = span_data.parent_span_id

        if not validate_trace_id(trace_id) or trace_id == "0" * 32:
            return None
        if not validate_span_id(parent_span_id) or parent_span_id == "0" * 16:
            parent_span_id = _generate_span_id()

        parent_span_context = self._sdk_modules.span_context_cls(
            trace_id=int(trace_id, 16),
            span_id=int(parent_span_id, 16),
            is_remote=True,
            trace_flags=self._sdk_modules.trace_flags_cls(
                self._sdk_modules.trace_flags_cls.SAMPLED
            ),
            trace_state=self._sdk_modules.trace_state_cls(),
        )
        return cast(
            object,
            self._sdk_modules.set_span_in_context(
                self._sdk_modules.non_recording_span_cls(parent_span_context)
            ),
        )


def _resolve_otel_sink_config(config: JSONObject) -> OTELSinkConfig:
    """Resolve OTEL sink config from settings with per-sink overrides."""
    settings = get_settings()

    enabled = bool(config.get("enabled", settings.otel_enabled))

    endpoint_value = config.get("endpoint", settings.otel_endpoint)
    endpoint = str(endpoint_value) if endpoint_value else None

    headers_value = config.get("headers", settings.otel_headers)
