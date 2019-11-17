"""Helpers for parsing stored control definitions consistently."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from agent_control_models import ControlDefinition, ControlDefinitionRuntime
from agent_control_models.errors import ErrorCode, ValidationErrorItem
from pydantic import ValidationError

from ..errors import APIValidationError
from .validation_paths import format_field_path


def build_control_validation_errors(
    validation_error: ValidationError,
    *,
    field_prefix: str | None = "data",
) -> list[ValidationErrorItem]:
    """Convert ControlDefinition validation errors into API error items."""
    items: list[ValidationErrorItem] = []
    for err in validation_error.errors():
        loc = cast(Sequence[str | int], err.get("loc", ()))
        field_suffix = format_field_path(loc)
        if field_prefix is None:
            field = field_suffix
        elif field_suffix is None:
            field = field_prefix
        else:
