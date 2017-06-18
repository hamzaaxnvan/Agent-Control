"""BudgetStore abstract base class -- interface for budget storage backends.

Implementations must provide atomic record-and-check: a single call
that records usage and returns the current totals. This prevents
read-then-write race conditions under concurrent access.

Built-in: InMemoryBudgetStore (dict + threading.Lock).
External: Redis, PostgreSQL, etc. (separate packages).
"""

from __future__ import annotations

import inspect
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import BudgetLimitRule


@dataclass(frozen=True)
class BudgetSnapshot:
    """Immutable view of budget state at a point in time.

    Attributes:
        spent: Cumulative spend in cents (USD), rounded from float.
        spent_tokens: Cumulative tokens (input + output) in this scope+period.
        limit: Configured ceiling, interpreted by limit_unit.
        utilization: Selected usage ratio clamped to [0.0, 1.0].
        exceeded: True when the configured limit is breached.
        limit_unit: Unit used to interpret limit.
    """

    spent: int
    spent_tokens: int
    limit: int | None
    utilization: float
    exceeded: bool
    limit_unit: str = "usd_cents"
