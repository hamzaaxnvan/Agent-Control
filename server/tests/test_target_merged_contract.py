"""End-to-end coverage for the merged effective-controls contract.

``initAgent``, ``GET /agents/{name}/controls`` and ``POST /evaluation``
all return the same de-duplicated union of:

- the agent's direct controls,
- policy-derived controls,
- and (when target context is supplied) controls bound to that target via
  enabled bindings in the same namespace.

These tests pin that all three surfaces agree on the same set for the
same inputs.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

import pytest
from agent_control_server.auth_framework import Operation, Principal, set_authorizer
from fastapi import Request
from fastapi.testclient import TestClient

from .utils import VALID_CONTROL_PAYLOAD, canonicalize_control_payload


class RecordingAuthorizer:
    """Authorizer that records operation/context pairs for endpoint contract tests."""

    def __init__(self, *, target_namespace_key: str = "default") -> None:
        self.calls: list[tuple[Operation, dict[str, Any] | None]] = []
        self.target_namespace_key = target_namespace_key

    async def authorize(
        self,
        request: Request,
        operation: Operation,
        context: dict[str, Any] | None = None,
    ) -> Principal:
        del request
        self.calls.append((operation, context))
        namespace_key = (
            self.target_namespace_key
            if operation is Operation.CONTROL_BINDINGS_READ and context is not None
            else "default"
        )
        return Principal(namespace_key=namespace_key, is_admin=True)


def _agent_payload(
    agent_name: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent": {
            "agent_name": agent_name,
            "agent_description": "",
            "agent_version": "1.0",
        },
        "steps": [],
    }
    if target_type is not None:
        payload["target_type"] = target_type
    if target_id is not None:
        payload["target_id"] = target_id
    return payload


def _register_agent(
    client: TestClient,
    agent_name: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/agents/initAgent",
        json=_agent_payload(agent_name, target_type=target_type, target_id=target_id),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_control(client: TestClient, *, name: str | None = None) -> int:
    payload = canonicalize_control_payload(deepcopy(VALID_CONTROL_PAYLOAD))
    resp = client.put(
        "/api/v1/controls",
        json={"name": name or f"control-{uuid.uuid4().hex[:12]}", "data": payload},
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["control_id"])


def _bind(
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


def _attach_direct(client: TestClient, agent_name: str, control_id: int) -> None:
    resp = client.post(f"/api/v1/agents/{agent_name}/controls/{control_id}")
    assert resp.status_code == 200, resp.text


def _list_effective_via_get(
    client: TestClient,
    agent_name: str,
    *,
