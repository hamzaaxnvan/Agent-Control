"""Tests for initAgent conflict_mode behavior."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from agent_control_models.errors import ErrorCode
from fastapi import Request
from fastapi.testclient import TestClient

from agent_control_server.auth_framework import Operation, Principal, set_authorizer
from agent_control_server.errors import ForbiddenError

from .utils import VALID_CONTROL_PAYLOAD


class CreateOnlyAuthorizer:
    async def authorize(
        self,
        request: Request,
        operation: Operation,
        context: dict[str, Any] | None = None,
    ) -> Principal:
        del request, context
        if operation is Operation.AGENTS_UPDATE:
            raise ForbiddenError(
                error_code=ErrorCode.AUTH_INSUFFICIENT_PRIVILEGES,
                detail="update denied",
            )
        return Principal(namespace_key="default", is_admin=True)


def _init_payload(
    *,
    agent_name: str,
    agent_description: str = "desc",
    agent_version: str = "1.0",
    steps: list[dict[str, Any]] | None = None,
    evaluators: list[dict[str, Any]] | None = None,
    conflict_mode: str | None = None,
) -> dict[str, Any]:
    canonical_name = agent_name.lower()
    payload: dict[str, Any] = {
        "agent": {
            "agent_name": canonical_name,
            "agent_description": agent_description,
            "agent_version": agent_version,
        },
        "steps": steps or [],
        "evaluators": evaluators or [],
    }
    if conflict_mode is not None:
        payload["conflict_mode"] = conflict_mode
    return payload


def _create_policy_with_agent_evaluator_control(
    client: TestClient,
    *,
    agent_name: str,
    evaluator_name: str,
) -> tuple[int, int, str]:
    control_data = deepcopy(VALID_CONTROL_PAYLOAD)
    control_name = f"control-{uuid.uuid4().hex[:8]}"
    control_data["condition"]["evaluator"] = {
        "name": f"{agent_name}:{evaluator_name}",
        "config": {},
    }
    create_control_resp = client.put(
        "/api/v1/controls", json={"name": control_name, "data": control_data}
    )
    assert create_control_resp.status_code == 200
    control_id = create_control_resp.json()["control_id"]

    policy_name = f"policy-{uuid.uuid4().hex[:8]}"
    create_policy_resp = client.put("/api/v1/policies", json={"name": policy_name})
    assert create_policy_resp.status_code == 200
    policy_id = create_policy_resp.json()["policy_id"]

    assoc_resp = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    assert assoc_resp.status_code == 200

    return policy_id, control_id, control_name


def test_init_agent_overwrite_replaces_steps_and_evaluators(client: TestClient) -> None:
    # Given: an existing agent registration with baseline steps and evaluators.
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"

    create_payload = _init_payload(
        agent_name=agent_name,
        steps=[
            {
                "type": "tool",
                "name": "tool-a",
