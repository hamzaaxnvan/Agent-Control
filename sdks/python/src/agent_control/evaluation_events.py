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
) -> tuple[str | None, str | None, dict[str, object]]:
    """Return representative event fields plus full composite context."""
    identity = control_def.observability_identity()
    return (
        identity.selector_path,
        identity.evaluator_name,
        {
            "primary_evaluator": identity.evaluator_name,
            "primary_selector_path": identity.selector_path,
            "leaf_count": identity.leaf_count,
            "all_evaluators": identity.all_evaluators,
            "all_selector_paths": identity.all_selector_paths,
        },
    )


def map_applies_to(step_type: str) -> str:
    """Map Agent Control step types to observability applies_to values."""
    if step_type == "tool":
        return "tool_call"
    if step_type == "llm":
        return "llm_call"
    return f"{step_type}_call"


def _resolve_event_trace_context(
    trace_id: str | None,
    span_id: str | None,
) -> tuple[str, str]:
    """Return event IDs, applying fallback IDs and a one-time warning if needed."""
    global _trace_warning_logged  # noqa: PLW0603

    if trace_id and span_id:
        return trace_id, span_id

    if not _trace_warning_logged:
        _logger.warning(
            "Emitting control events without trace context; events will use fallback "
            "IDs and cannot be correlated with traces. Pass trace_id/span_id for "
            "full observability."
        )
        _trace_warning_logged = True

    return trace_id or _FALLBACK_TRACE_ID, span_id or _FALLBACK_SPAN_ID


def _build_events_for_matches(
    matches: list[ControlMatch] | None,
    *,
    matched: bool,
