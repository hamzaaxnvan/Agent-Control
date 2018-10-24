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
        "name": name,
        "description": description or "",
        "input_schema": input_schema or {},
    }
    return definition


def normalize_strands_tool_specs(specs: object) -> list[JSONObject] | None:
    """Normalize a complete Strands tool-spec collection, if available."""
    if not isinstance(specs, list):
        return None

    normalized: list[JSONObject] = []
    for spec in specs:
        if not isinstance(spec, dict):
            return None
        name = spec.get("name")
