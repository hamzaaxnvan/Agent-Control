#!/usr/bin/env python3
"""Set up the target-context demo: agent + two controls + one binding.

Layout:

- ``block-pii-output`` is attached directly to the agent. It applies on
  every call regardless of target context.
- ``block-prod-restricted-input`` is bound to ``(env, prod)`` via a
  control binding. It applies only when the SDK's session target is
  ``(env, prod)`` and is omitted from the merged set otherwise.

When the demo agent calls ``init(target_type="env", target_id="prod")``,
the server returns the de-duplicated union: both controls. Re-init for a
different ``env`` value (or no target) drops the prod-bound control from
the returned set.

Prerequisites:
    - Agent Control server running at AGENT_CONTROL_URL (default localhost:8000).

Usage:
    uv run python examples/target_context_demo/setup_controls.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

# Add the SDK to path for development.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../sdks/python/src"))

from agent_control import AgentControlClient

AGENT_NAME = "demo-target-bot"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

PII_CONTROL_NAME = "block-pii-output"
PROD_CONTROL_NAME = "block-prod-restricted-input"

PII_CONTROL: dict[str, Any] = {
    "description": "Block SSN-like patterns in agent output (always on).",
    "enabled": True,
    "execution": "server",
    "scope": {"step_types": ["llm"], "stages": ["post"]},
    "condition": {
        "selector": {"path": "output"},
        "evaluator": {
            "name": "regex",
            "config": {"pattern": r"\b\d{3}-\d{2}-\d{4}\b", "flags": []},
        },
    },
    "action": {"decision": "deny"},
    "tags": ["pii", "agent-attached"],
}

PROD_CONTROL: dict[str, Any] = {
    "description": "Reject restricted input keywords on prod.",
    "enabled": True,
    "execution": "server",
    "scope": {"step_types": ["llm"], "stages": ["pre"]},
    "condition": {
        "selector": {"path": "input"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["DROP TABLE", "rm -rf", "sudo"],
                "logic": "any",
                "match_on": "match",
                "match_mode": "contains",
                "case_sensitive": False,
            },
        },
    },
    "action": {"decision": "deny"},
    "tags": ["env-bound", "prod-only"],
}


async def _create_or_get_control(
    client: AgentControlClient, name: str, definition: dict[str, Any]
) -> int:
    """Create a control by name; return its ID. Surfaces 409 cleanly."""
    response = await client.http_client.put(
        "/api/v1/controls",
        json={"name": name, "data": definition},
    )
    if response.status_code == 409:
        # Control already exists from a previous run — look it up.
        page = await client.http_client.get(
            "/api/v1/controls", params={"name": name}
        )
        page.raise_for_status()
        for entry in page.json().get("controls", []):
            if entry.get("name") == name:
                return int(entry["id"])
