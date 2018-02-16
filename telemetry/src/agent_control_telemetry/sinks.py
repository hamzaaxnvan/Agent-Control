"""Shared sink contracts for control execution event delivery."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from agent_control_models import ControlExecutionEvent


@dataclass(frozen=True)
class SinkResult:
    """Summarizes the outcome of a sink write attempt."""

    accepted: int
    dropped: int = 0

    @property
