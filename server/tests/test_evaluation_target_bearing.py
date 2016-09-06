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
    assert resp.status_code == 200, resp.text
    return int(resp.json()["control_id"])


def _create_binding(
    client: TestClient,
    *,
    control_id: int,
    target_type: str = "env",
    target_id: str = "prod",
    enabled: bool = True,
) -> int:
    body: dict[str, Any] = {
        "target_type": target_type,
        "target_id": target_id,
        "control_id": control_id,
        "enabled": enabled,
    }
    resp = client.put("/api/v1/control-bindings", json=body)
    assert resp.status_code == 200, resp.text
    return int(resp.json()["binding_id"])


def _evaluate(
    client: TestClient,
    *,
    agent_name: str,
    target_type: str | None = None,
    target_id: str | None = None,
    input_text: str = "x marks the spot",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "agent_name": agent_name,
        "step": {
            "type": "llm",
            "name": "test-step",
            "input": input_text,
            "context": {},
        },
        "stage": "pre",
    }
    if target_type is not None:
        body["target_type"] = target_type
