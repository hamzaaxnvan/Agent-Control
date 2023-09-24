"""Budget evaluator -- tracks cumulative LLM token/cost usage.

Deterministic evaluator: confidence is always 1.0, matched is True when
any configured limit is exceeded. Utilization ratio and spend breakdown
are returned in result metadata, not in confidence.

The evaluator is stateless. Budget state lives in a module-level store
registry, independent of the evaluator instance cache in _factory.py.
This prevents silent state loss on LRU eviction and avoids cross-control
leakage when different controls use different budget_id values.
"""

from __future__ import annotations

import logging
import math
import threading
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_control_evaluators._base import Evaluator, EvaluatorMetadata
from agent_control_evaluators._registry import register_evaluator
from agent_control_models import EvaluatorResult

from .config import BudgetEvaluatorConfig, ModelPricing
from .memory_store import InMemoryBudgetStore, _scope_matches
from .store import BudgetStore

logger = logging.getLogger(__name__)


def _resolve_package_version() -> str:
    """Return the installed package version, or a dev fallback during local imports."""
    try:
        return version("agent-control-evaluator-budget")
    except PackageNotFoundError:
        return "0.0.0.dev"


_PACKAGE_VERSION = _resolve_package_version()

# ---------------------------------------------------------------------------
# Module-level store registry
#
# Decoupled from the evaluator instance cache so that LRU eviction in
# _factory.py does not destroy accumulated budget state. The registry
# is keyed by budget_id. Controls with the same budget_id intentionally
# share accumulated spend; different budget_id values are isolated.
# ---------------------------------------------------------------------------

# NOTE: The registry is unbounded. In practice a deployment has a finite
# set of budget configs. If dynamic config generation becomes a concern,
# add a max-size cap with LRU eviction here.
_STORE_REGISTRY: dict[str, BudgetStore] = {}
_STORE_REGISTRY_LOCK = threading.Lock()


def get_or_create_store(config: BudgetEvaluatorConfig) -> BudgetStore:
    """Get or create a store for the given config, thread-safe."""
    key = f"budget:{config.budget_id}"
    with _STORE_REGISTRY_LOCK:
