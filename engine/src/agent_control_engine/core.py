"""Core logic for the control engine.

Evaluates controls in parallel with cancel-on-deny for efficiency.
"""

import asyncio
import functools
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import re2
from agent_control_evaluators import get_evaluator_instance
from agent_control_models import (
    ConditionNode,
    ControlAction,
    ControlMatch,
    ControlScope,
    EvaluationRequest,
    EvaluationResponse,
    EvaluatorResult,
    JSONObject,
)

from .selectors import select_data

logger = logging.getLogger(__name__)


def _env_positive_int(*names: str, default: int) -> int:
    """Read a positive integer from the first configured environment variable."""
    for name in names:
        value = os.environ.get(name)
        if value is None or value.strip() == "":
            continue
        try:
            parsed = int(value)
        except ValueError as exc:
            raise RuntimeError(f"{name}={value!r} must be an integer.") from exc
        if parsed < 1:
            raise RuntimeError(f"{name}={value!r} must be greater than or equal to 1.")
        return parsed
    return default


# Default timeout for evaluator execution (seconds)
DEFAULT_EVALUATOR_TIMEOUT = float(os.environ.get("EVALUATOR_TIMEOUT_SECONDS", "30"))

# Max concurrent evaluations (limits task spawning overhead for large policies).
# Prefer the namespaced env var; MAX_CONCURRENT_EVALUATIONS is kept for compatibility.
MAX_CONCURRENT_EVALUATIONS = _env_positive_int(
    "AGENT_CONTROL_MAX_CONCURRENT_EVALUATIONS",
    "MAX_CONCURRENT_EVALUATIONS",
    default=3,
)

SELECTED_DATA_PREVIEW_MAX_CHARS = int(
    os.environ.get("AGENT_CONTROL_SELECTED_DATA_PREVIEW_MAX_CHARS", "500")
)
SELECTED_DATA_PREVIEW_MAX_ITEMS = int(
    os.environ.get("AGENT_CONTROL_SELECTED_DATA_PREVIEW_MAX_ITEMS", "20")
)
SELECTED_DATA_PREVIEW_MAX_DEPTH = int(
    os.environ.get("AGENT_CONTROL_SELECTED_DATA_PREVIEW_MAX_DEPTH", "3")
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Read a boolean environment flag."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key is likely to contain a secret."""
    normalized = str(key).lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _truncate_string(value: str, max_chars: int) -> tuple[str, bool]:
    """Return a bounded string preview and whether it was truncated."""
    if len(value) <= max_chars:
        return value, False
    if max_chars <= 3:
        return value[:max_chars], True
    return f"{value[: max_chars - 3]}...", True


def _selected_data_preview_value(
    value: Any,
    *,
    depth: int = 0,
) -> tuple[Any, bool]:
    """Build a bounded, redacted preview of selected data."""
    if depth >= SELECTED_DATA_PREVIEW_MAX_DEPTH:
        return "<max depth reached>", True

    if value is None or isinstance(value, bool | int | float):
        return value, False

    if isinstance(value, str):
        return _truncate_string(value, SELECTED_DATA_PREVIEW_MAX_CHARS)

    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        truncated = len(value) > SELECTED_DATA_PREVIEW_MAX_ITEMS
        for index, (key, item) in enumerate(value.items()):
            if index >= SELECTED_DATA_PREVIEW_MAX_ITEMS:
                break
            preview_key = str(key)
            if _is_sensitive_key(key):
                preview[preview_key] = "<redacted>"
                truncated = True
                continue
            preview_item, item_truncated = _selected_data_preview_value(
                item,
                depth=depth + 1,
            )
            preview[preview_key] = preview_item
            truncated = truncated or item_truncated
        return preview, truncated

    if isinstance(value, list | tuple):
        preview_items: list[Any] = []
        truncated = len(value) > SELECTED_DATA_PREVIEW_MAX_ITEMS
        for item in value[:SELECTED_DATA_PREVIEW_MAX_ITEMS]:
            preview_item, item_truncated = _selected_data_preview_value(
                item,
                depth=depth + 1,
            )
            preview_items.append(preview_item)
            truncated = truncated or item_truncated
        return preview_items, truncated

    text_preview, truncated = _truncate_string(str(value), SELECTED_DATA_PREVIEW_MAX_CHARS)
    return text_preview, truncated


def _selected_data_preview(value: Any) -> dict[str, Any]:
    """Return UI-safe selector output details for evaluator-level inspection."""
    preview, truncated = _selected_data_preview_value(value)
    return {
        "type": type(value).__name__,
        "value": preview,
        "truncated": truncated,
    }


@functools.lru_cache(maxsize=256)
def _compile_regex(pattern: str) -> Any:
    """Compile and cache RE2 regex patterns.

    Caching avoids recompiling the same pattern on every request.
    """
    return re2.compile(pattern)


class ControlDefinitionLike(Protocol):
    """Runtime control shape required by the engine."""

    enabled: bool
    execution: Literal["server", "sdk"]
    scope: ControlScope
    condition: ConditionNode
    action: ControlAction


class ControlWithIdentity(Protocol):
    """Protocol for a control with identity information."""

    @property
    def id(self) -> int:
        """Database identity for the control."""

    @property
    def name(self) -> str:
        """Human-readable name for the control."""

    @property
    def control(self) -> ControlDefinitionLike:
        """Runtime control payload used during evaluation."""


@dataclass
class _EvalTask:
    """Internal container for evaluation task context."""

    item: ControlWithIdentity
    task: asyncio.Task[None] | None = None
    result: EvaluatorResult | None = None
    execution_duration_ms: float | None = None


@dataclass
class _ConditionEvaluation:
    """Internal result for recursive condition evaluation."""

