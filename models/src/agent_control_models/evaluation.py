"""Evaluation-related models."""
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from .agent import AGENT_NAME_MIN_LENGTH, AGENT_NAME_PATTERN, Step, normalize_agent_name
from .base import BaseModel
from .controls import ControlMatch

_TARGET_FIELD = Annotated[
    str | None,
    StringConstraints(min_length=1, max_length=255),
]


class EvaluationRequest(BaseModel):
    """
    Request model for evaluation analysis.

    Used to analyze agent interactions for safety violations,
    policy compliance, and control rules.

    Attributes:
        agent_name: Unique identifier of the agent making the request
        step: Step payload for evaluation
        stage: 'pre' (before execution) or 'post' (after execution)
        target_type: Optional opaque target kind. When set together with
            ``target_id``, the server merges controls bound to that target
            into the effective set, in addition to the agent's direct and
            policy-derived controls.
        target_id: Optional opaque target identifier. Required when
            ``target_type`` is set.
    """
    agent_name: str = Field(
        ...,
        min_length=AGENT_NAME_MIN_LENGTH,
        pattern=AGENT_NAME_PATTERN,
        description="Identifier of the agent making the evaluation request",
    )
    step: Step = Field(
        ..., description="Agent step payload to evaluate"
