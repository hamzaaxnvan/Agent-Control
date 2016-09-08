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
            return value

        normalized = value.strip()
        if not normalized:
            raise ValueError("Evaluator name cannot be empty or whitespace-only.")
        return normalized

    @model_validator(mode="after")
    def validate_evaluator_config(self) -> Self:
        """Validate config against evaluator's schema if evaluator is registered.

        Agent-scoped evaluators (format: agent:evaluator) are validated in the
        endpoint where we have database access to look up the agent's schema.
        """
        # Agent-scoped evaluators: defer validation to endpoint (needs DB access)
        if ":" in self.name:
            return self

        # Built-in evaluators: validate config against evaluator's config_model
        # This import is optional - evaluators package may not be installed
        try:
            from agent_control_evaluators import ensure_evaluators_discovered, get_evaluator

            # Ensure entry points are loaded before looking up evaluator
            ensure_evaluators_discovered()
            evaluator_cls = get_evaluator(self.name)
            if evaluator_cls:
                evaluator_cls.config_model(**self.config)
        except ImportError:
            # Evaluators package not installed - skip validation
            pass

        # If evaluator not found, allow it (might be a server-side registered evaluator)
        return self


type ConditionLeafParts = tuple[ControlSelector, EvaluatorSpec]


@dataclass(frozen=True)
class ControlObservabilityIdentity:
    """Stable selector/evaluator identity derived from a condition tree."""

    selector_path: str | None
    evaluator_name: str | None
    leaf_count: int
    all_evaluators: list[str]
    all_selector_paths: list[str]


class SteeringContext(BaseModel):
    """Steering context for steer actions.

    This model provides an extensible structure for steering guidance.
    Future fields could include severity, categories, suggested_actions, etc.
    """

    message: str = Field(
        ...,
        description="Guidance message explaining what needs to be corrected and how"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": (
                        "This large transfer requires user verification. "
                        "Request 2FA code from user, verify it, then retry "
                        "the transaction with verified_2fa=True."
                    )
                },
                {
                    "message": (
                        "Transfer exceeds daily limit. Steps: "
                        "1) Ask user for business justification, "
                        "2) Request manager approval with amount and justification, "
                        "3) If approved, retry with manager_approved=True and "
                        "justification filled in."
                    )
                }
            ]
        }
    }


type TemplateValue = str | bool | list[str]
type JsonValue = JSONValue

MAX_CONDITION_DEPTH = 12
_TEMPLATE_PARAMETER_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
MAX_TEMPLATE_DEFINITION_DEPTH = MAX_CONDITION_DEPTH
MAX_TEMPLATE_DEFINITION_NODES = 1000


def _validate_re2_value(value: str, *, field_name: str) -> str:
    """Validate that a string is a valid RE2 expression."""
    try:
        re2.compile(value)
    except re2.error as exc:
        raise ValueError(f"Invalid {field_name}: {exc}") from exc
    return value


def _validate_template_definition_structure(value: JsonValue) -> JsonValue:
    """Validate template definition nesting and overall size."""
    stack: list[tuple[JsonValue, int]] = [(value, 1)]
    node_count = 0

    while stack:
        node, depth = stack.pop()
        node_count += 1

        if depth > MAX_TEMPLATE_DEFINITION_DEPTH:
            raise ValueError(
                "definition_template nesting depth exceeds maximum of "
                f"{MAX_TEMPLATE_DEFINITION_DEPTH}"
            )

        if node_count > MAX_TEMPLATE_DEFINITION_NODES:
            raise ValueError(
                "definition_template size exceeds maximum of "
                f"{MAX_TEMPLATE_DEFINITION_NODES} JSON nodes"
            )

        if isinstance(node, dict):
            stack.extend((nested_value, depth + 1) for nested_value in node.values())
        elif isinstance(node, list):
            # List elements inherit parent depth — a flat array of strings is
            # not structurally deeper than a single value.
            stack.extend((nested_value, depth) for nested_value in node)

    return value


class TemplateParameterBase(BaseModel):
    """Base definition for a template parameter."""

    label: str = Field(..., min_length=1, description="Human-readable parameter label")
    description: str | None = Field(
        None,
        description="Optional description of what the parameter controls",
    )
    required: bool = Field(
        True,
        description="Whether the caller must provide a value when no default exists",
    )
    ui_hint: str | None = Field(
        None,
        description="Optional UI hint for rendering the parameter input",
    )


class StringTemplateParameter(TemplateParameterBase):
    """String-valued template parameter."""

    type: Literal["string"] = "string"
    default: str | None = Field(None, description="Optional default value")
    placeholder: str | None = Field(None, description="Optional placeholder text")


class StringListTemplateParameter(TemplateParameterBase):
    """List-of-strings template parameter."""

    type: Literal["string_list"] = "string_list"
    default: list[str] | None = Field(None, description="Optional default value")
    placeholder: list[str] | None = Field(
        None,
        description="Optional placeholder/example list",
    )

    @field_validator("default", "placeholder")
    @classmethod
    def validate_string_lists(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is None:
            return value
        if any((not isinstance(item, str)) for item in value):
            raise ValueError("Values must be strings")
        return value


class EnumTemplateParameter(TemplateParameterBase):
    """String enum template parameter."""

    type: Literal["enum"] = "enum"
    allowed_values: list[str] = Field(
        ...,
        min_length=1,
        description="Allowed string values for the parameter",
    )
    default: str | None = Field(None, description="Optional default value")

    @field_validator("allowed_values")
