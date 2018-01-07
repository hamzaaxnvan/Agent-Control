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

