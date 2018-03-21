"""Evaluator discovery endpoints."""

from typing import Any

from agent_control_engine import list_evaluators
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth_framework import Operation, require_operation

router = APIRouter(prefix="/evaluators", tags=["evaluators"])


class EvaluatorInfo(BaseModel):
    """Information about a registered evaluator."""

    name: str = Field(..., description="Evaluator name")
    version: str = Field(..., description="Evaluator version")
    description: str = Field(..., description="Evaluator description")
    requires_api_key: bool = Field(..., description="Whether evaluator requires API key")
    timeout_ms: int = Field(..., description="Default timeout in milliseconds")
    config_schema: dict[str, Any] = Field(..., description="JSON Schema for config")


@router.get(
    "",
    response_model=dict[str, EvaluatorInfo],
    summary="List available evaluators",
    response_description="Dictionary of evaluator name to evaluator info",
