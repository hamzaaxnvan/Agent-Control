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


def validate_action(action: str) -> ActionDecision:
    """Validate that *action* is one of the canonical action values.

    Use this on public API boundaries (control create/update, query filters)
    where legacy values should be rejected.
    """
    if action in _CANONICAL_ACTIONS:
        return cast(ActionDecision, action)
    raise ValueError(
        f"Invalid action {action!r}. Must be one of: deny, steer, observe."
    )


def validate_action_list(actions: Sequence[str]) -> list[ActionDecision]:
    """Validate a list of actions, preserving order and removing duplicates."""
