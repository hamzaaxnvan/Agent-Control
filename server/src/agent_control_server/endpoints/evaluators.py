"""Evaluator discovery endpoints."""

from typing import Any

from agent_control_engine import list_evaluators
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth_framework import Operation, require_operation

router = APIRouter(prefix="/evaluators", tags=["evaluators"])


class EvaluatorInfo(BaseModel):
