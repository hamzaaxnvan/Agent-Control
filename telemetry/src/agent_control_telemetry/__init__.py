"""Shared telemetry contracts for Agent Control."""

from .sink_selection import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
    ControlEventSinkFactory,
    ControlEventSinkFactoryRegistry,
    ControlEventSinkSelection,
    SinkSelectionError,
)
