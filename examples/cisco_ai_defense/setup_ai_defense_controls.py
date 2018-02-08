"""Setup Cisco AI Defense controls and attach to an agent.

This script creates two controls (pre: input, post: output) that use the
external evaluator `cisco.ai_defense`, then attaches them directly to the
specified agent by name. The operations are idempotent and safe to rerun.

Env:
  AGENT_CONTROL_URL      - server base URL (e.g., http://localhost:8000)
  AGENT_CONTROL_API_KEY  - server API key (sent as X-API-Key)
  AGENT_NAME             - agent name to attach controls to (default: ai-defense-demo)
  AI_DEFENSE_API_URL     - optional override endpoint for evaluator config
  AI_DEFENSE_TIMEOUT_S   - optional timeout for evaluator config (default 15)
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from agent_control import Agent, AgentControlClient, agents, controls

EVALUATOR_NAME = "cisco.ai_defense"


def _headers() -> dict[str, str]:
    api_key = os.getenv("AGENT_CONTROL_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


def _make_control_names(agent_name: str) -> tuple[str, str]:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", agent_name).strip("-") or "agent"
    return (f"ai-defense-pre-{safe}", f"ai-defense-post-{safe}")


async def _ensure_control(
    client: AgentControlClient, *, name: str, data: dict[str, Any]
) -> int:
    """Create a control or reuse an existing one by name (idempotent)."""
    try:
        result = await controls.create_control(client, name=name, data=data)
        return int(result["control_id"])  # type: ignore[index]
    except Exception as e:  # noqa: BLE001
        s = str(e).lower()
        if "409" in s or "already" in s:
            cursor: int | None = None
            while True:
                existing = await controls.list_controls(client, name=name, limit=100, cursor=cursor)
                items = existing.get("controls", [])
                for item in items:
                    if item.get("name") == name:
                        return int(item["id"])  # type: ignore[index]

                pagination = existing.get("pagination", {})
                if not pagination.get("has_more"):
                    break
                next_cursor = pagination.get("next_cursor")
