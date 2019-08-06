"""Test utilities for server tests."""
import uuid
from copy import deepcopy
from typing import Any

from agent_control_models import ControlDefinition
from fastapi.testclient import TestClient

VALID_CONTROL_PAYLOAD = {
    "description": "Valid Control",
    "enabled": True,
    "execution": "server",
    "scope": {"step_types": ["llm"], "stages": ["pre"]},
    "condition": {
        "selector": {"path": "input"},
        "evaluator": {"name": "regex", "config": {"pattern": "x"}},
    },
    "action": {"decision": "deny"}
}


def canonicalize_control_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy flat test payloads into canonical condition trees."""
    canonical = ControlDefinition.canonicalize_payload(deepcopy(payload))
    if not isinstance(canonical, dict):
        raise TypeError("Control payload canonicalization must return a dict.")
    return canonical
