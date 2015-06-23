"""Shared control-action types and normalization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

type ActionDecision = Literal["deny", "steer", "observe"]

_CANONICAL_ACTIONS = frozenset({"deny", "steer", "observe"})
_OBSERVE_ACTION_ALIASES = frozenset({"allow", "observe", "warn", "log"})
_ACTION_QUERY_EXPANSION: dict[ActionDecision, tuple[str, ...]] = {
    "deny": ("deny",),
    "steer": ("steer",),
    "observe": ("observe", "allow", "warn", "log"),
}
