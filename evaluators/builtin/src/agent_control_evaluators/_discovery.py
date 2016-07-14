"""Evaluator discovery via entry points."""

from __future__ import annotations

import logging
import threading
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any

from agent_control_evaluators._registry import (
    get_all_evaluators,
    get_evaluator,
    register_evaluator,
)

if TYPE_CHECKING:
    from agent_control_evaluators._base import Evaluator

logger = logging.getLogger(__name__)

_DISCOVERY_COMPLETE = False
_DISCOVERY_LOCK = threading.Lock()


def discover_evaluators() -> int:
    """Discover and register evaluators via entry points.

    All evaluators (built-in and third-party) are discovered via the
    'agent_control.evaluators' entry point group. Evaluators are only registered
    if their `is_available()` method returns True.

    Safe to call multiple times - only runs discovery once.
    Thread-safe via lock.

    Returns:
        Number of evaluators discovered
    """
    global _DISCOVERY_COMPLETE

    # Fast path without lock
    if _DISCOVERY_COMPLETE:
        return 0

    with _DISCOVERY_LOCK:
        # Double-check after acquiring lock
        if _DISCOVERY_COMPLETE:
            return 0

        discovered = 0

        # Discover ALL evaluators (built-in and third-party) via entry points.
        # Only register evaluators where is_available() returns True.
        try:
            eps = entry_points(group="agent_control.evaluators")
