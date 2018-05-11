"""Evaluation analysis endpoints."""

import json
from dataclasses import dataclass

from agent_control_engine.core import ControlEngine
from agent_control_models import (
    ControlDefinitionRuntime,
    ControlMatch,
    EvaluationRequest,
    EvaluationResponse,
    JSONObject,
)
from agent_control_models.errors import ErrorCode, ValidationErrorItem
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from ..auth_framework import Operation, Principal, require_operation
from ..db import AsyncSessionLocal
from ..errors import APIValidationError, NotFoundError
from ..logging_utils import get_logger
from ..models import Agent
from ..services.controls import ControlService

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

_logger = get_logger(__name__)

SAFE_EVALUATOR_ERROR = "Evaluation failed due to an internal evaluator error."
SAFE_EVALUATOR_TIMEOUT_ERROR = "Evaluation timed out before completion."
SAFE_INVALID_STEP_REGEX_ERROR = "Control configuration error: invalid step name regex."
SAFE_ENGINE_VALIDATION_MESSAGE = "Invalid evaluation request or control configuration."


@dataclass
class ControlAdapter:
    """Adapts API Control to Engine ControlWithIdentity protocol."""

    id: int
    name: str
    control: ControlDefinitionRuntime


def _sanitize_evaluator_error(error_message: str) -> str:
    """Convert evaluator runtime errors into safe client-facing text."""
    if "invalid step_name_regex" in error_message.lower():
        return SAFE_INVALID_STEP_REGEX_ERROR
