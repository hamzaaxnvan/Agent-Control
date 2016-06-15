"""Schema derivation helpers for agent step registration.

This module centralizes JSON schema derivation so registry code can focus on
bookkeeping (naming, metadata, and deduplication) rather than inference logic.

Derivation is best-effort:
- Prefer framework-provided ``args_schema`` for input if available.
- Otherwise infer schemas from function type hints using Pydantic.
- On inference failures, log a warning and return permissive fallback schemas.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import TypeAdapter, create_model

logger = logging.getLogger(__name__)

_INPUT_FALLBACK_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}
_OUTPUT_FALLBACK_SCHEMA: dict[str, Any] = {}


@dataclass(frozen=True)
class DerivedSchemas:
    """Container for derived input/output JSON schemas."""

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


def derive_schemas(func: Callable[..., Any]) -> DerivedSchemas:
    """Derive input/output JSON schemas for a function.

    Args:
        func: Function for schema derivation.

    Returns:
        DerivedSchemas containing input and output JSON schemas.
    """
    input_schema_override = _extract_args_schema_override(func)
    unwrapped = inspect.unwrap(func)

    try:
        hints = get_type_hints(unwrapped, include_extras=True)
    except Exception as exc:
        if input_schema_override is not None:
            _warn(
                func,
                phase="output",
                reason="failed to resolve type hints",
                exc=exc,
                fallback=_OUTPUT_FALLBACK_SCHEMA,
            )
            return DerivedSchemas(
                input_schema=input_schema_override,
                output_schema=_fallback_output_schema(),
            )

        _warn(
            func,
            phase="input/output",
            reason="failed to resolve type hints",
            exc=exc,
            fallback={
                "input": _INPUT_FALLBACK_SCHEMA,
                "output": _OUTPUT_FALLBACK_SCHEMA,
            },
        )
        return DerivedSchemas(
            input_schema=_fallback_input_schema(),
            output_schema=_fallback_output_schema(),
        )

    input_schema = input_schema_override
    if input_schema is None:
        input_schema = _infer_input_schema(func, unwrapped, hints)

    output_schema = _infer_output_schema(func, hints)
    return DerivedSchemas(input_schema=input_schema, output_schema=output_schema)


def _extract_args_schema_override(func: Callable[..., Any]) -> dict[str, Any] | None:
    """Extract framework-provided input schema from ``func.args_schema``."""
    args_schema = getattr(func, "args_schema", None)
    if args_schema is None:
        return None
    if not hasattr(args_schema, "model_json_schema"):
        return None

    try:
        schema = args_schema.model_json_schema()
    except Exception as exc:  # pragma: no cover - exercised via tests with caplog
        _warn(
            func,
            phase="input",
            reason="args_schema.model_json_schema() failed; using signature inference",
            exc=exc,
            fallback=_INPUT_FALLBACK_SCHEMA,
        )
        return None

    if not isinstance(schema, dict):
        _warn(
            func,
            phase="input",
            reason="args_schema.model_json_schema() returned non-dict; using signature inference",
            fallback=_INPUT_FALLBACK_SCHEMA,
        )
        return None

    return schema


def _infer_input_schema(
    func: Callable[..., Any],
    unwrapped: Callable[..., Any],
    hints: dict[str, Any],
) -> dict[str, Any]:
    """Infer input schema from signature + type hints using dynamic Pydantic model."""

    try:
        signature = inspect.signature(unwrapped)
    except Exception as exc:
