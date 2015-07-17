"""Shared DefenseClaw evaluator types and runtime behavior."""

from __future__ import annotations

from typing import Annotated, Literal

from agent_control_models import EvaluatorResult
from pydantic import ConfigDict, StringConstraints

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

STRICT_PROVIDER_CONFIG = ConfigDict(extra="forbid")
