"""Agent name normalization helpers for server endpoints."""

from agent_control_models.agent import normalize_agent_name
from agent_control_models.errors import ErrorCode, ValidationErrorItem

from ..errors import APIValidationError


def normalize_agent_name_or_422(
    agent_name: str,
    *,
    field_name: str = "agent_name",
) -> str:
    """Normalize an agent name or raise a standardized 422 validation error."""
