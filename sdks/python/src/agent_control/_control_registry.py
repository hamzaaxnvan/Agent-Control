"""Registry for @control()-decorated functions.

Tracks step schemas (name, type, input/output schema) from decorated functions
so they can be auto-populated into ``init(steps=...)`` without the user having
to specify them manually.

Registration happens at **decoration time** (import time), so all decorated
functions are captured before ``init()`` is called -- as long as ``init()``
is called after the module containing the decorated functions has been imported.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from ._schema_derivation import derive_schemas
from .validation import ensure_step_type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step schema types
# ---------------------------------------------------------------------------

type StepKey = tuple[str, str]


class StepSchemaDict(TypedDict):
    """Runtime representation of a step schema payload."""

    type: str
    name: str
    description: NotRequired[str]
    input_schema: NotRequired[dict[str, Any] | None]
    output_schema: NotRequired[dict[str, Any] | None]
    metadata: NotRequired[dict[str, Any]]


@dataclass(frozen=True)
class StepMergeResult:
    """Result of merging explicit and auto-discovered step schemas."""

    steps: list[StepSchemaDict]
    overridden_keys: list[StepKey]


@dataclass(frozen=True)
class _RegisteredControl:
    """Internal metadata stored at decorator-registration time."""

    func: Callable[..., Any]
    step_type: str
    step_name: str
    description: str | None
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Internal registry
# ---------------------------------------------------------------------------

_registered_steps: dict[StepKey, _RegisteredControl] = {}
"""Maps ``(type, name)`` -> registration metadata. Keyed by type+name to deduplicate."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register(
    func: Callable[..., Any],
    policy: str | None = None,
    step_type: str | None = None,
) -> None:
    """Register a decorated function's step schema in the registry.

    Extracts step metadata from the function and stores it for later retrieval
    via ``get_registered_steps()``.

    Input/output schema derivation is intentionally deferred to retrieval time
    so forward references are more likely to be resolvable by the time
    ``init()`` runs.

    Args:
        func: The original (unwrapped) function being decorated.
        policy: Optional policy name (stored as metadata).
        step_type: Optional explicit step type. When omitted, tool-like
            functions are registered as ``tool`` and other functions as ``llm``.
    """
    # Determine step name -- tools typically have .name or .tool_name
    tool_name = getattr(func, "name", None) or getattr(func, "tool_name", None)
    step_name: str = tool_name if isinstance(tool_name, str) else func.__name__
    resolved_step_type = (
        ensure_step_type(step_type)
        if step_type is not None
        else ("tool" if isinstance(tool_name, str) else "llm")
    )

    # Extract description from docstring (first line only)
    description: str | None = None
    if func.__doc__:
        first_line = func.__doc__.strip().split("\n")[0].strip()
        if first_line:
            description = first_line

    metadata: dict[str, Any] = {}
    if policy is not None:
        metadata["policy"] = policy

    key = _step_key(resolved_step_type, step_name)
    registered = _RegisteredControl(
        func=func,
        step_type=resolved_step_type,
        step_name=step_name,
        description=description,
        metadata=metadata,
