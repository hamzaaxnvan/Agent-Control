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
    def success(self) -> bool:
        """Return True when at least one event was accepted."""
        return self.accepted > 0


class ControlEventSink(Protocol):
    """Write-side abstraction for delivering control execution events."""

    def write_events(self, events: Sequence[ControlExecutionEvent]) -> SinkResult:
        """Write a batch of control execution events."""


class BaseControlEventSink(ControlEventSink):
    """Minimal helper base for sink implementations."""

    def is_active(self) -> bool:
        """Return whether the sink is currently able to deliver events."""
        return True

