"""Shared sink-selection models and registries for control-event delivery."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import TypeVar

from agent_control_models import JSONObject
from pydantic import BaseModel, Field

DEFAULT_CONTROL_EVENT_SINK_NAME = "default"
REGISTERED_CONTROL_EVENT_SINK_NAME = "registered"

SinkT = TypeVar("SinkT")
type ControlEventSinkFactory[SinkT] = Callable[[JSONObject], SinkT]


class SinkSelectionError(LookupError):
    """Raised when a configured sink cannot be resolved."""


class ControlEventSinkSelection(BaseModel):
    """Runtime-agnostic sink-selection payload.

    This model intentionally shares only the selection shape across runtimes.
    The meaning of built-in sink names such as ``default`` or ``registered``,
    along with any supported config keys, is defined by the caller/runtime
    that resolves the selection.
    """

    name: str = Field(
        default=DEFAULT_CONTROL_EVENT_SINK_NAME,
        min_length=1,
        description=(
            "Sink selection name. Built-in names are interpreted by the runtime "
            "that resolves this selection."
        ),
    )
    config: JSONObject = Field(
        default_factory=dict,
        description=(
            "Runtime-specific configuration for the selected sink. Shared only "
            "as a transport shape, not as cross-runtime semantics."
        ),
    )
