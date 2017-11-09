"""Evaluator registry for registration and lookup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_control_evaluators._base import Evaluator

logger = logging.getLogger(__name__)

# =============================================================================
# Evaluator Registry
# =============================================================================

_EVALUATOR_REGISTRY: dict[str, type[Evaluator[Any]]] = {}


def register_evaluator(
    evaluator_class: type[Evaluator[Any]],
) -> type[Evaluator[Any]]:
    """Register an evaluator class by its metadata name.

    Can be used as a decorator or called directly. Respects the evaluator's
    is_available() method - evaluators with unavailable dependencies are
    silently skipped.

    Args:
        evaluator_class: Evaluator class to register

    Returns:
        The same evaluator class (for decorator usage)

    Raises:
        ValueError: If evaluator name already registered with different class

    Example:
        ```python
        @register_evaluator
        class MyEvaluator(Evaluator[MyConfig]):
            metadata = EvaluatorMetadata(name="my-evaluator", ...)
            ...
