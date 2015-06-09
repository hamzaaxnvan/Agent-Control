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
