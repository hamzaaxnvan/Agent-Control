"""Control definition models for agent protection."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

import re2
from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from .actions import ActionDecision, normalize_action, validate_action
from .agent import JSONValue
from .base import BaseModel


class ControlSelector(BaseModel):
    """Selects data from a Step payload.

    - path: which slice of the Step to feed into the evaluator. Optional, defaults to "*"
      meaning the entire Step object.
    """

    path: str | None = Field(
        default="*",
        description=(
            "Path to data using dot notation. "
            "Examples: 'input', 'output', 'context.user_id', 'name', 'type', '*'"
        ),
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str | None) -> str:
        """Validate path; None becomes '*', empty string raises."""
        if v is None:
            return "*"
        if v == "":
            raise ValueError(
                "Path cannot be empty string. Use '*' for root or omit the field."
            )

        # Valid root fields
        valid_roots = {"input", "output", "name", "type", "context", "*"}
        root = v.split(".")[0]

        if root not in valid_roots:
            raise ValueError(
                f"Invalid path root '{root}'. "
                f"Must be one of: {', '.join(sorted(valid_roots))}"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"path": "output"},
                {"path": "context.user_id"},
                {"path": "input"},
                {"path": "*"},
                {"path": "name"},
                {"path": "output"},
            ]
        }
    }


class ControlScope(BaseModel):
    """Defines when a control applies to a Step."""

    step_types: list[str] | None = Field(
        default=None,
        description=(
            "Step types this control applies to (omit to apply to all types). "
            "Built-in types are 'tool' and 'llm'."
        ),
        examples=[["llm"], ["tool"], ["llm", "tool"]],
    )
    step_names: list[str] | None = Field(
        default=None,
        description="Exact step names this control applies to",
    )
    step_name_regex: str | None = Field(
        default=None,
        description="RE2 pattern matched with search() against step name",
    )
    stages: list[Literal["pre", "post"]] | None = Field(
        default=None,
        description="Evaluation stages this control applies to",
    )

    @field_validator("step_types")
    @classmethod
    def validate_step_types(
        cls, v: list[str] | None
    ) -> list[str] | None:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError(
                "step_types cannot be an empty list. Use None/omit the field to apply to all types."
            )
        if any((not isinstance(x, str) or not x) for x in v):
            raise ValueError("step_types must be a list of non-empty strings")
        return v

    @field_validator("step_names")
    @classmethod
    def validate_step_names(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError(
                "step_names cannot be an empty list. Use None/omit the field to apply to all steps."
            )
        if any((not isinstance(x, str) or not x) for x in v):
            raise ValueError("step_names must be a list of non-empty strings")
        return v

    @field_validator("step_name_regex")
    @classmethod
    def validate_step_name_regex(
        cls, v: str | None, info: ValidationInfo
    ) -> str | None:
        if v is None:
            return v
        if info.context and info.context.get("allow_invalid_step_name_regex"):
            return v
        try:
            re2.compile(v)
        except re2.error as e:
            raise ValueError(f"Invalid step_name_regex: {e}") from e
        return v

    @field_validator("stages")
    @classmethod
    def validate_stages(
        cls, v: list[Literal["pre", "post"]] | None
    ) -> list[Literal["pre", "post"]] | None:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError(
                "stages cannot be an empty list. Use None/omit the field to apply to all stages."
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"step_types": ["tool"], "stages": ["pre"]},
                {"step_names": ["search_db", "fetch_user"]},
                {"step_name_regex": "^db_.*"},
                {"step_types": ["llm"], "stages": ["post"]},
            ]
        }
    }


# =============================================================================
# Unified Evaluator Spec (used in API)
# =============================================================================


class EvaluatorSpec(BaseModel):
    """Evaluator specification. See GET /evaluators for available evaluators and schemas.

    Evaluator reference formats:
    - Built-in: "regex", "list", "json", "sql"
    - External: "galileo.luna" (requires agent-control-evaluators[galileo])
    - Agent-scoped: "my-agent:my-evaluator" (validated in endpoint, not here)
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Evaluator name or agent-scoped reference (agent:evaluator)",
        examples=["regex", "list", "my-agent:pii-detector"],
    )
    config: dict[str, Any] = Field(
        ...,
        description="Evaluator-specific configuration",
        examples=[
            {"pattern": r"\d{3}-\d{2}-\d{4}"},
            {"values": ["admin"], "logic": "any"},
        ],
    )

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not isinstance(value, str):
