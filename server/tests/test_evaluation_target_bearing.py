"""End-to-end coverage for evaluation requests with target context.

The evaluation endpoint resolves the same merged effective set as
``initAgent`` and ``GET /agents/{name}/controls``: the de-duplicated
union of the agent's direct controls, policy-derived controls, and (when
``target_type`` and ``target_id`` are both supplied) controls bound to
that target via enabled bindings in the same namespace.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from fastapi.testclient import TestClient

from .utils import VALID_CONTROL_PAYLOAD, canonicalize_control_payload


def _agent_payload(agent_name: str) -> dict[str, Any]:
    return {
        "agent": {
            "agent_name": agent_name,
            "agent_description": "test agent",
            "agent_version": "1.0",
        },
        "steps": [],
    }


def _register_agent(client: TestClient, agent_name: str) -> None:
    resp = client.post("/api/v1/agents/initAgent", json=_agent_payload(agent_name))
    assert resp.status_code == 200, resp.text


def _create_control(client: TestClient) -> int:
    payload = canonicalize_control_payload(deepcopy(VALID_CONTROL_PAYLOAD))
    resp = client.put(
        "/api/v1/controls",
        json={"name": f"control-{uuid.uuid4().hex[:12]}", "data": payload},
    )
