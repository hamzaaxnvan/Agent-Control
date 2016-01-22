from __future__ import annotations

import json
import uuid
from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from agent_control_server.models import Control

from .utils import VALID_CONTROL_PAYLOAD, canonicalize_control_payload
from .conftest import engine


def _init_agent(
    client: TestClient,
    *,
    agent_name: str | None = None,
    steps: list[dict] | None = None,
    evaluators: list[dict] | None = None,
) -> tuple[str, str]:
    name = (agent_name or f"agent-{uuid.uuid4().hex[:12]}").lower()
    if len(name) < 10:
        name = f"{name}-agent".replace("--", "-")
    payload = {
        "agent": {
            "agent_name": name,
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": steps or [],
        "evaluators": evaluators or [],
    }
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    assert resp.status_code == 200
    return name, name


def _create_control_with_data(client: TestClient, data: dict) -> int:
    resp = client.put(
        "/api/v1/controls",
        json={
            "name": f"control-{uuid.uuid4()}",
            "data": canonicalize_control_payload(data),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["control_id"]


def _create_template_control_with_data(client: TestClient, data: dict) -> int:
    resp = client.put(
        "/api/v1/controls",
        json={
            "name": f"control-{uuid.uuid4()}",
            "data": data,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["control_id"]


def _unrendered_template_payload() -> dict:
    return {
        "template": {
            "description": "Regex denial template",
            "parameters": {
                "pattern": {
                    "type": "regex_re2",
                    "label": "Pattern",
                },
            },
            "definition_template": {
                "description": "Template-backed control",
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "regex",
                        "config": {"pattern": {"$param": "pattern"}},
                    },
                },
                "action": {"decision": "deny"},
            },
        },
        "template_values": {},
    }


def _insert_unconfigured_control() -> int:
    control = Control(name=f"control-{uuid.uuid4()}", data={})
    with Session(engine) as session:
        session.add(control)
        session.commit()
        session.refresh(control)
        return int(control.id)


def _create_policy(client: TestClient) -> int:
    resp = client.put("/api/v1/policies", json={"name": f"policy-{uuid.uuid4()}"})
    assert resp.status_code == 200
    return resp.json()["policy_id"]


def test_list_agent_evaluators_pagination_and_get(client: TestClient) -> None:
    # Given: an agent with multiple evaluators
    evaluators = [
        {"name": "eval-a", "description": "a", "config_schema": {}},
        {"name": "eval-b", "description": "b", "config_schema": {"type": "object"}},
        {"name": "eval-c", "description": "c", "config_schema": {}},
    ]
    agent_name, _ = _init_agent(client, evaluators=evaluators)

    # When: listing with pagination
    resp = client.get(f"/api/v1/agents/{agent_name}/evaluators", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    # Then: first page returns two items and a next cursor
    assert len(body["evaluators"]) == 2
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["next_cursor"] == "eval-b"

    # When: fetching next page using cursor
    resp2 = client.get(
        f"/api/v1/agents/{agent_name}/evaluators",
        params={"limit": 2, "cursor": body["pagination"]["next_cursor"]},
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    # Then: second page has remaining item and no next cursor
    assert body2["pagination"]["has_more"] is False
    assert [e["name"] for e in body2["evaluators"]] == ["eval-c"]

    # When: getting a specific evaluator
    get_resp = client.get(f"/api/v1/agents/{agent_name}/evaluators/eval-b")
    assert get_resp.status_code == 200
    evaluator = get_resp.json()
    # Then: evaluator details are returned
    assert evaluator["name"] == "eval-b"
    assert evaluator["description"] == "b"


def test_list_agent_evaluators_invalid_cursor_returns_first_page(client: TestClient) -> None:
    # Given: an agent with multiple evaluators
    evaluators = [
        {"name": "eval-a", "description": "a", "config_schema": {}},
        {"name": "eval-b", "description": "b", "config_schema": {}},
    ]
    agent_name, _ = _init_agent(client, evaluators=evaluators)

    # When: listing without cursor
    resp = client.get(f"/api/v1/agents/{agent_name}/evaluators", params={"limit": 1})
    assert resp.status_code == 200
    base = resp.json()

    # When: listing with an invalid cursor
    resp2 = client.get(
        f"/api/v1/agents/{agent_name}/evaluators",
        params={"limit": 1, "cursor": "does-not-exist"},
    )
    assert resp2.status_code == 200
    with_cursor = resp2.json()

    # Then: results match the first page
    assert with_cursor["evaluators"] == base["evaluators"]
    assert with_cursor["pagination"]["total"] == base["pagination"]["total"]


def test_init_agent_preserves_existing_steps_when_missing_from_payload(
    client: TestClient,
) -> None:
    # Given: an agent registered with two steps
    steps = [
        {"type": "tool", "name": "tool-a", "input_schema": {}, "output_schema": {}},
        {"type": "tool", "name": "tool-b", "input_schema": {}, "output_schema": {}},
    ]
    agent_name, agent_name = _init_agent(client, steps=steps)

    # When: re-initializing with only one of the steps
    payload = {
        "agent": {
            "agent_name": agent_name,
            "agent_name": agent_name,
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": [steps[0]],
        "evaluators": [],
    }
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    assert resp.status_code == 200

    # Then: the missing step is preserved (initAgent only adds)
    get_resp = client.get(f"/api/v1/agents/{agent_name}")
    assert get_resp.status_code == 200
    step_names = {step["name"] for step in get_resp.json()["steps"]}
    assert step_names == {"tool-a", "tool-b"}


def test_get_agent_evaluator_not_found(client: TestClient) -> None:
    # Given: an existing agent with no matching evaluator
    agent_name, _ = _init_agent(client)

    # When: requesting a missing evaluator
    resp = client.get(f"/api/v1/agents/{agent_name}/evaluators/missing")

    # Then: 404 not found
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "EVALUATOR_NOT_FOUND"


def test_get_agent_evaluator_missing_agent_returns_404(client: TestClient) -> None:
    # Given: a missing agent id
    missing_agent = str(uuid.uuid4())

    # When: fetching evaluator for missing agent
    resp = client.get(f"/api/v1/agents/{missing_agent}/evaluators/anything")

    # Then: agent not found error is returned
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "AGENT_NOT_FOUND"


def test_patch_agent_remove_steps_and_evaluators(client: TestClient) -> None:
    # Given: an agent with steps and evaluators
    steps = [
        {"type": "tool", "name": "tool-a", "input_schema": {}, "output_schema": {}},
        {"type": "tool", "name": "tool-b", "input_schema": {}, "output_schema": {}},
    ]
    evaluators = [
        {"name": "eval-a", "description": "a", "config_schema": {}},
        {"name": "eval-b", "description": "b", "config_schema": {}},
    ]
    agent_name, _ = _init_agent(client, steps=steps, evaluators=evaluators)

    # When: removing one step and one evaluator
    resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={
            "remove_steps": [{"type": "tool", "name": "tool-a"}],
            "remove_evaluators": ["eval-b"],
        },
    )

    # Then: response lists removed items
    assert resp.status_code == 200
    body = resp.json()
    assert body["steps_removed"] == [{"type": "tool", "name": "tool-a"}]
    assert body["evaluators_removed"] == ["eval-b"]

    # Then: agent data reflects removal
    get_resp = client.get(f"/api/v1/agents/{agent_name}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert {s["name"] for s in data["steps"]} == {"tool-b"}
    assert {e["name"] for e in data["evaluators"]} == {"eval-a"}


def test_patch_agent_remove_evaluator_in_use_conflict(client: TestClient) -> None:
    # Given: agent with evaluator and a policy containing a control that references it
    evaluators = [
        {
            "name": "custom",
            "description": "custom",
            "config_schema": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        }
    ]
    agent_name, agent_name = _init_agent(client, evaluators=evaluators)

    control_payload = deepcopy(VALID_CONTROL_PAYLOAD)
    control_payload["condition"]["evaluator"] = {
        "name": f"{agent_name}:custom",
        "config": {"pattern": "x"},
    }
