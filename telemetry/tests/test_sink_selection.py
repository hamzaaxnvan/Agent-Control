"""Tests for shared control-event sink selection helpers."""

from agent_control_telemetry import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
    ControlEventSinkFactoryRegistry,
    ControlEventSinkSelection,
    SinkSelectionError,
)


def test_control_event_sink_selection_defaults_to_builtin_sink() -> None:
    selection = ControlEventSinkSelection()

    assert selection.name == DEFAULT_CONTROL_EVENT_SINK_NAME
    assert selection.config == {}


def test_sink_factory_registry_resolves_registered_factory() -> None:
    registry: ControlEventSinkFactoryRegistry[str] = ControlEventSinkFactoryRegistry()
    registry.register("custom", lambda config: f"sink:{config['target']}")

    resolved = registry.resolve(
        ControlEventSinkSelection(name="custom", config={"target": "demo"})
    )
