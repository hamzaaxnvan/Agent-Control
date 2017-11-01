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
    if "timeout" in error_message.lower():
        return SAFE_EVALUATOR_TIMEOUT_ERROR
    return SAFE_EVALUATOR_ERROR


def _sanitize_condition_trace(trace: object) -> object:
    """Recursively redact internal evaluator errors from condition traces."""
    if isinstance(trace, list):
        return [_sanitize_condition_trace(item) for item in trace]

    if not isinstance(trace, dict):
        return trace

    sanitized = {
        key: _sanitize_condition_trace(value)
        for key, value in trace.items()
    }

    raw_error = sanitized.get("error")
    if isinstance(raw_error, str) and raw_error:
        safe_error = _sanitize_evaluator_error(raw_error)
        sanitized["error"] = safe_error
        raw_message = sanitized.get("message")
        if raw_message is None or isinstance(raw_message, str):
            sanitized["message"] = safe_error

    return sanitized


def _sanitize_control_match(match: ControlMatch) -> ControlMatch:
    """Redact internal evaluator error strings from a control match."""
    if match.result.error is None:
        return match

    safe_error = _sanitize_evaluator_error(match.result.error)
    safe_message = safe_error
    metadata = dict(match.result.metadata or {})
    condition_trace = metadata.get("condition_trace")
    if condition_trace is not None:
        metadata["condition_trace"] = _sanitize_condition_trace(condition_trace)
    sanitized_result = match.result.model_copy(
        update={
            "error": safe_error,
            "message": safe_message,
            "metadata": metadata or None,
        }
    )
