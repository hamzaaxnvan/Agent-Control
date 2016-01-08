"""Normalization helpers for complete framework tool registries."""

from __future__ import annotations

from typing import Any

from agent_control_models import JSONObject, JSONValue


def normalized_tool_definition(
    *,
    name: str,
    description: str | None,
    input_schema: dict[str, Any] | None,
) -> JSONObject:
    """Return the framework-neutral available-tool representation."""
    definition: dict[str, JSONValue] = {
