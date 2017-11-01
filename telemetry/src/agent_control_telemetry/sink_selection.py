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
