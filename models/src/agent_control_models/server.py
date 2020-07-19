import datetime as dt
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from .agent import Agent, StepSchema
from .base import BaseModel
from .controls import (
    ControlAction,
    ControlDefinition,
    TemplateControlInput,
    TemplateDefinition,
    TemplateValue,
    UnrenderedTemplateControl,
)
from .policy import Control


def _strip_slug_name(v: str) -> str:
    """Strip leading/trailing whitespace for slug-style names."""
    return v.strip() if isinstance(v, str) else v


_CONTROL_DEFINITION_ADAPTER = TypeAdapter(ControlDefinition)
_TEMPLATE_CONTROL_INPUT_ADAPTER = TypeAdapter(TemplateControlInput)
_TEMPLATE_ONLY_CONTROL_FIELDS = frozenset({"template", "template_values"})
_RAW_CONTROL_INPUT_FIELDS = (
    frozenset(ControlDefinition.model_fields) - _TEMPLATE_ONLY_CONTROL_FIELDS
)
_RAW_CONTROL_INPUT_FIELDS = _RAW_CONTROL_INPUT_FIELDS.union(
    {
        # Legacy flat leaf fields still accepted for raw controls.
        "selector",
        "evaluator",
    }
)


def _parse_control_input(v: Any) -> Any:
    """Discriminate raw control inputs from template-backed inputs.

    A non-null ``template`` key means template-backed input and must be parsed
    strictly as ``TemplateControlInput`` so mixed payloads are rejected.
    """
    if isinstance(v, (ControlDefinition, TemplateControlInput)):
        return v
    if not isinstance(v, dict):
        return v

    if v.get("template") is not None:
        mixed_fields = sorted(field for field in v if field in _RAW_CONTROL_INPUT_FIELDS)
        if mixed_fields:
            raise ValueError(
                "Template-backed control input cannot mix template fields with rendered control "
                f"fields. Remove raw fields: {', '.join(mixed_fields)}."
            )
        return _TEMPLATE_CONTROL_INPUT_ADAPTER.validate_python(v)
    return _CONTROL_DEFINITION_ADAPTER.validate_python(v)


# Canonicalization at the API boundary: all SlugName fields are trimmed before
# validation. Server and SDKs use these request models; no client need pre-trim.
SlugName = Annotated[
    str,
    BeforeValidator(_strip_slug_name),
    StringConstraints(
        min_length=1,
        max_length=255,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$",
    ),
]

ControlInput = Annotated[
    ControlDefinition | TemplateControlInput,
    BeforeValidator(_parse_control_input),
]


class EvaluatorSchema(BaseModel):
    """Schema for a custom evaluator registered with an agent.

    Custom evaluators are Evaluator classes deployed with the engine.
    This schema is registered via initAgent for validation and UI purposes.
    """

    name: str = Field(..., min_length=1, max_length=255, description="Unique evaluator name")
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for evaluator config validation",
    )
    description: str | None = Field(None, max_length=1000, description="Optional description")


class ConflictMode(StrEnum):
    """Conflict handling mode for initAgent registration updates.

    STRICT preserves compatibility checks and raises conflicts on incompatible changes.
    OVERWRITE applies latest-init-wins replacement for steps and evaluators.
    """

    STRICT = "strict"
    OVERWRITE = "overwrite"


class InitAgentEvaluatorRemoval(BaseModel):
    """Details for an evaluator removed during overwrite mode."""

    name: str = Field(..., description="Evaluator name removed by overwrite")
    referenced_by_active_controls: bool = Field(
        default=False,
        description="Whether this evaluator is still referenced by active controls",
    )
    control_ids: list[int] = Field(
        default_factory=list,
        description="IDs of active controls referencing this evaluator",
    )
    control_names: list[str] = Field(
        default_factory=list,
        description="Names of active controls referencing this evaluator",
    )


class InitAgentOverwriteChanges(BaseModel):
    """Detailed change summary for initAgent overwrite mode."""

    metadata_changed: bool = Field(
        default=False, description="Whether agent metadata changed"
    )
    steps_added: list["StepKey"] = Field(
        default_factory=list,
        description="Steps added by overwrite",
    )
    steps_updated: list["StepKey"] = Field(
        default_factory=list,
        description="Existing steps updated by overwrite",
    )
    steps_removed: list["StepKey"] = Field(
        default_factory=list,
        description="Steps removed by overwrite",
    )
    evaluators_added: list[str] = Field(
        default_factory=list,
        description="Evaluator names added by overwrite",
    )
    evaluators_updated: list[str] = Field(
        default_factory=list,
        description="Existing evaluator names updated by overwrite",
    )
    evaluators_removed: list[str] = Field(
        default_factory=list,
        description="Evaluator names removed by overwrite",
    )
    evaluator_removals: list[InitAgentEvaluatorRemoval] = Field(
        default_factory=list,
        description="Per-evaluator removal details, including active control references",
    )


class CreatePolicyRequest(BaseModel):
    name: SlugName = Field(
        ...,
        description="Unique policy name (letters, numbers, hyphens, underscores)",
    )


class CreateControlRequest(BaseModel):
    name: SlugName = Field(
        ...,
        description="Unique control name (letters, numbers, hyphens, underscores)",
    )
    data: ControlInput = Field(
        ...,
        description="Control definition to validate and store during creation",
    )


class InitAgentRequest(BaseModel):
    """Request to initialize or update an agent registration."""

    agent: Agent = Field(..., description="Agent metadata including ID, name, and version")
    steps: list[StepSchema] = Field(
        default_factory=list, description="List of steps available to the agent"
    )
    evaluators: list[EvaluatorSchema] = Field(
        default_factory=list,
        description="Custom evaluator schemas for config validation",
    )
    force_replace: bool = Field(
        default=False,
        description=(
            "If true, replace corrupted agent data instead of failing. "
            "Use only when agent data is corrupted and cannot be parsed."
        ),
    )
    conflict_mode: ConflictMode = Field(
        default=ConflictMode.STRICT,
        description=(
            "Conflict handling mode for init registration updates. "
            "'strict' preserves existing compatibility checks. "
            "'overwrite' applies latest-init-wins replacement for steps and evaluators."
        ),
    )
    target_type: Annotated[
        str | None, StringConstraints(min_length=1, max_length=255)
    ] = Field(
        default=None,
        description=(
            "Optional opaque target kind. When supplied with target_id, the "
            "returned controls include controls bound to that target via "
            "control bindings, in addition to the agent's direct and "
            "policy-derived controls."
        ),
    )
    target_id: Annotated[
        str | None, StringConstraints(min_length=1, max_length=255)
    ] = Field(
        default=None,
        description=(
            "Optional opaque target identifier. Required when target_type is "
            "supplied."
        ),
    )

    @model_validator(mode="after")
    def _check_target_pair(self) -> Self:
        if (self.target_type is None) != (self.target_id is None):
            raise ValueError(
                "target_type and target_id must be supplied together."
            )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "agent": {
                        "agent_name": "customer-service-bot",
                        "agent_description": "Handles customer inquiries",
                        "agent_version": "1.0.0",
                    },
                    "steps": [
                        {
                            "type": "tool",
                            "name": "search_kb",
                            "input_schema": {"query": {"type": "string"}},
                            "output_schema": {"results": {"type": "array"}},
                        }
                    ],
                    "evaluators": [
                        {
                            "name": "pii-detector",
                            "config_schema": {
                                "type": "object",
                                "properties": {"sensitivity": {"type": "string"}},
                            },
                            "description": "Detects PII in text",
                        }
                    ],
                }
            ]
        }
    }


class InitAgentResponse(BaseModel):
    """Response from agent initialization."""
    created: bool = Field(
        ..., description="True if agent was newly created, False if updated"
    )
    controls: list[Control] = Field(
        default_factory=list,
        description="Active protection controls for the agent",
    )
    overwrite_applied: bool = Field(
        default=False,
        description="True if overwrite mode changed registration data on an existing agent",
    )
    overwrite_changes: InitAgentOverwriteChanges = Field(
        default_factory=InitAgentOverwriteChanges,
        description="Detailed list of changes applied in overwrite mode",
    )


class GetAgentResponse(BaseModel):
