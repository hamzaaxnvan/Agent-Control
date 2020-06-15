"""Derived control-execution event reconstruction for SDK evaluation flows."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from agent_control_engine.selectors import select_data
from agent_control_models import (
    ControlDefinition,
    ControlDefinitionRuntime,
    ControlExecutionEvent,
    ControlMatch,
    EvaluationRequest,
    EvaluationResponse,
)

from .observability import get_logger, is_observability_enabled, write_events

_logger = get_logger(__name__)

# All-zero values are invalid trace/span IDs per OpenTelemetry and make it
# obvious that the event could not be correlated to an external trace.
_FALLBACK_TRACE_ID = "0" * 32
_FALLBACK_SPAN_ID = "0" * 16
_trace_warning_logged = False
_DEBUG_METADATA_KEYS = frozenset(
    {
        "selected_data",
        "selected_data_preview",
        "engine_selected_data",
        "engine_selected_data_preview",
    }
)


def _safe_event_metadata(metadata: dict[str, object]) -> dict[str, object]:
    """Drop raw/debug metadata that should not be exported as observability data."""
    safe_metadata = {k: v for k, v in metadata.items() if k not in _DEBUG_METADATA_KEYS}
    if "input" not in safe_metadata:
        for preview_key in ("engine_selected_data_preview", "selected_data_preview"):
            preview = metadata.get(preview_key)
            if isinstance(preview, dict) and "value" in preview:
                safe_metadata["input"] = preview["value"]
                break
    return safe_metadata


def observability_metadata(
    control_def: ControlDefinition | ControlDefinitionRuntime,
