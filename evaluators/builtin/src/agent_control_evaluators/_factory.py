"""Evaluator factory with instance caching."""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from agent_control_evaluators._discovery import list_evaluators

if TYPE_CHECKING:
    from agent_control_models import EvaluatorSpec

    from agent_control_evaluators._base import Evaluator

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_CACHE_SIZE = 100
MIN_CACHE_SIZE = 1  # Minimum to avoid infinite loop in eviction


def _parse_cache_size() -> int:
    """Parse EVALUATOR_CACHE_SIZE from env with safe fallback."""
    raw = os.environ.get("EVALUATOR_CACHE_SIZE")
    if raw is None:
        return DEFAULT_CACHE_SIZE
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            f"Invalid EVALUATOR_CACHE_SIZE '{raw}', using default {DEFAULT_CACHE_SIZE}"
        )
        return DEFAULT_CACHE_SIZE


EVALUATOR_CACHE_SIZE = max(_parse_cache_size(), MIN_CACHE_SIZE)

# LRU cache for evaluator instances: cache_key -> Evaluator instance
_EVALUATOR_CACHE: OrderedDict[str, Evaluator[Any]] = OrderedDict()


def _config_hash(config: dict[str, Any]) -> str:
    """Create a hashable key from config dict."""
    return json.dumps(config, sort_keys=True, default=str)


def get_evaluator_instance(evaluator_spec: EvaluatorSpec) -> Evaluator[Any]:
    """Get or create a cached evaluator instance from specification.

