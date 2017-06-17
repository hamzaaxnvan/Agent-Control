"""In-memory budget store implementation.

Not suitable for multi-process deployments. For distributed setups,
use a Redis or Postgres-backed store (separate package).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .config import BudgetLimitRule
from .store import BudgetSnapshot, BudgetStore, round_spent


def _sanitize_scope_value(val: str) -> str:
    """Percent-encode pipe and equals in scope values to prevent key injection."""
    return val.replace("%", "%25").replace("|", "%7C").replace("=", "%3D")


def _build_scope_key(
    rule_scope: dict[str, str],
    group_by: str | None,
    step_scope: dict[str, str],
) -> str:
    """Build a composite scope key from rule dimensions and group_by field."""
    parts: list[str] = []
    for k, v in sorted(rule_scope.items()):
        parts.append(f"{k}={_sanitize_scope_value(v)}")
    if group_by and group_by in step_scope:
        parts.append(f"{group_by}={_sanitize_scope_value(step_scope[group_by])}")
    return "|".join(parts) if parts else "__global__"


def _parse_period_key(key: str) -> tuple[int, int] | None:
    """Parse 'P{window}:{index}' into (window_seconds, bucket_index).

    Returns None for empty/cumulative keys.
    """
    if not key or not key.startswith("P"):
        return None
    try:
        window_part, index_part = key[1:].split(":", 1)
        return int(window_part), int(index_part)
    except (ValueError, IndexError):
        return None


def _derive_period_key(window_seconds: int | None, now: float) -> str:
    """Derive a period key from window_seconds and a timestamp.

    Periods are aligned to UTC epoch boundaries. For example,
    window_seconds=86400 produces keys like "P86400:19800" where
    19800 is the number of complete windows since epoch.
    """
    if window_seconds is None:
        return ""
    period_index = int(now) // window_seconds
    return f"P{window_seconds}:{period_index}"


def _scope_matches(rule: BudgetLimitRule, scope: dict[str, str]) -> bool:
    """Check if rule's scope dimensions match step scope."""
    for key, expected in rule.scope.items():
        if scope.get(key) != expected:
            return False
    if rule.group_by and rule.group_by not in scope:
        return False
    return True


def _compute_utilization(
    spent: float,
    spent_tokens: int,
    limit: int | None,
    limit_unit: str,
) -> float:
    """Return the selected usage ratio clamped to [0.0, 1.0].

    The low-side clamp is load-bearing: under refund semantics the internal
