"""Evaluator base classes and metadata."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from agent_control_models import EvaluatorResult, JSONObject, Step
from agent_control_models.base import BaseModel

if TYPE_CHECKING:
    from typing import Self

logger = logging.getLogger(__name__)


class EvaluatorConfig(BaseModel):
    """Base class for typed evaluator configurations.

    Extends the project's BaseModel to ensure consistent behavior
    and enable type checking across all evaluator configs.

    Example:
        ```python
        from agent_control_evaluators import EvaluatorConfig

        class MyEvaluatorConfig(EvaluatorConfig):
            pattern: str
            threshold: float = 0.5
        ```
    """

    pass


ConfigT = TypeVar("ConfigT", bound=EvaluatorConfig)


@dataclass
class EvaluatorMetadata:
    """Metadata about an evaluator.

    Attributes:
        name: Unique evaluator name (e.g., "regex", "galileo.luna")
        version: Evaluator version string
        description: Human-readable description
        requires_api_key: Whether the evaluator requires an API key
        timeout_ms: Default timeout in milliseconds
    """

    name: str
    version: str
    description: str
    requires_api_key: bool = False
    timeout_ms: int = 10000


class Evaluator(ABC, Generic[ConfigT]):  # noqa: UP046 - need Python 3.10 compat
    """Base class for all evaluators (built-in, external, or custom).

    All evaluators follow the same pattern:
        1. Define metadata and config_model as class variables
        2. Implement evaluate() method
        3. Register with @register_evaluator decorator

    IMPORTANT - Instance Caching & Thread Safety:
        Evaluator instances are cached and reused across multiple evaluate() calls
        when they have the same configuration. This means:

        - DO NOT store mutable request-scoped state on `self`
        - The evaluate() method may be called concurrently from multiple requests
        - Any state stored in __init__ should be immutable or thread-safe
        - Use local variables within evaluate() for request-specific state

        Good pattern:
            def __init__(self, config):
                super().__init__(config)
                self._compiled_regex = re.compile(config.pattern)  # OK: immutable

            async def evaluate(self, data):
                result = self._compiled_regex.search(data)  # OK: uses immutable state
                return EvaluatorResult(matched=result is not None, ...)

        Bad pattern:
            def __init__(self, config):
                super().__init__(config)
                self.call_count = 0  # BAD: mutable state shared across requests

            async def evaluate(self, data):
                self.call_count += 1  # BAD: race condition, leaks between requests

    Example:
        ```python
        from agent_control_evaluators import (
            Evaluator,
            EvaluatorConfig,
            EvaluatorMetadata,
            register_evaluator,
        )
        from agent_control_models import EvaluatorResult

        class MyConfig(EvaluatorConfig):
