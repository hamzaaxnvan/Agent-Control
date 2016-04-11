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
    `spent` accumulator may go negative, which would otherwise produce a
    negative ratio and violate the BudgetSnapshot.utilization contract.
    """
    if limit_unit == "tokens":
        ratio = spent_tokens / limit if limit else 0.0
    else:
        ratio = spent / limit if limit else 0.0
    return max(0.0, min(ratio, 1.0))


@dataclass
class _Bucket:
    """Internal mutable accumulator for a single (scope, period) pair."""

    spent: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class InMemoryBudgetStore(BudgetStore):
    """Thread-safe in-memory budget store.

    Owns bucket state and derives period keys internally from
    window_seconds + injected clock. Callers provide the rules to evaluate
    on each record operation.

    Cost is accumulated as float for precision. Integer rounding
    happens only at snapshot time for display/reporting.

    TTL prune: on new period rollover per window, buckets older than
    `current - 1` for that window are dropped. This keeps memory bounded
    for long-running deployments with windowed rules.

    `max_buckets` remains as a backstop for high-cardinality group_by
    explosions that TTL cannot protect against.
    """

    _DEFAULT_MAX_BUCKETS = 100_000

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        max_buckets: int = _DEFAULT_MAX_BUCKETS,
    ) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._max_buckets = max_buckets
        self._last_pruned_period: dict[int, int] = {}

    async def record_and_check(
        self,
        rules: list[BudgetLimitRule],
        scope: dict[str, str],
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> list[BudgetSnapshot]:
        """Atomically record usage and return snapshots for all matching rules."""
        return self._record_and_check_sync(rules, scope, input_tokens, output_tokens, cost)

    def _record_and_check_sync(
        self,
        rules: list[BudgetLimitRule],
        scope: dict[str, str],
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> list[BudgetSnapshot]:
        """Sync implementation of record_and_check.

        NaN/Inf cost is coerced to 0.0 defensively. Once NaN enters a
        bucket's float accumulator, all subsequent additions produce NaN
        and `nan >= limit` is always False (IEEE 754), permanently
        disabling budget enforcement for that bucket.
        """
        if not math.isfinite(cost):
            cost = 0.0
