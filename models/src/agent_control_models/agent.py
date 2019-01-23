"""Agent entity and step models."""
from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import BaseModel

type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]

STEP_TYPE_TOOL = "tool"
STEP_TYPE_LLM = "llm"
BUILTIN_STEP_TYPES: tuple[str, str] = (STEP_TYPE_TOOL, STEP_TYPE_LLM)

AGENT_NAME_MIN_LENGTH = 10
AGENT_NAME_PATTERN = r"^[a-z0-9:_-]+$"
_AGENT_NAME_REGEX = re.compile(AGENT_NAME_PATTERN)


def normalize_agent_name(value: str) -> str:
    """Normalize and validate an agent identifier."""
    normalized = value.strip().lower()
    if len(normalized) < AGENT_NAME_MIN_LENGTH:
        raise ValueError(
            f"agent_name must be at least {AGENT_NAME_MIN_LENGTH} characters long"
        )
    if not _AGENT_NAME_REGEX.fullmatch(normalized):
        raise ValueError(
            "agent_name may only contain lowercase letters, digits, ':', '_' or '-'"
        )
    return normalized


class Agent(BaseModel):
    """
    Agent metadata for registration and tracking.

    An agent represents an AI system that can be protected and monitored.
    Each agent has a unique immutable name and can have multiple steps registered with it.
    """
    agent_name: str = Field(
        ...,
        min_length=AGENT_NAME_MIN_LENGTH,
        pattern=AGENT_NAME_PATTERN,
        description="Unique immutable identifier for the agent",
    )
    agent_description: str | None = Field(
        None, description="Optional description of the agent's purpose"
    )
    agent_created_at: str | None = Field(
        None, description="ISO 8601 timestamp when agent was created"
    )
    agent_updated_at: str | None = Field(
        None, description="ISO 8601 timestamp when agent was last updated"
    )
    agent_version: str | None = Field(
        None, description="Semantic version string (e.g. '1.0.0')"
    )
    agent_metadata: dict[str, Any] | None = Field(
        None, description="Free-form metadata dictionary for custom properties"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "agent_name": "customer-service-bot",
                    "agent_description": "Handles customer inquiries and support tickets",
                    "agent_version": "1.0.0",
                    "agent_metadata": {"team": "support", "environment": "production"}
                }
            ]
        }
