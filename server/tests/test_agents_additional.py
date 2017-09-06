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
    control_id = _create_control_with_data(client, control_payload)

    policy_id = _create_policy(client)
    assoc = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    assert assoc.status_code == 200
    assign = client.post(f"/api/v1/agents/{agent_name}/policy/{policy_id}")
    assert assign.status_code == 200

    # When: attempting to remove evaluator in use
    resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={"remove_evaluators": ["custom"]},
    )

    # Then: conflict
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "EVALUATOR_IN_USE"


def test_set_agent_policy_incompatible_controls(client: TestClient) -> None:
    # Given: a policy with a control referencing an evaluator from Agent A
    evaluators = [
        {
            "name": "custom",
            "description": "custom",
            "config_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        }
    ]
    agent_a_id, agent_a_name = _init_agent(client, evaluators=evaluators)

    control_payload = deepcopy(VALID_CONTROL_PAYLOAD)
    control_payload["condition"]["evaluator"] = {
        "name": f"{agent_a_name}:custom",
        "config": {},
    }
    control_id = _create_control_with_data(client, control_payload)

    policy_id = _create_policy(client)
    assoc = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    assert assoc.status_code == 200

    # Given: a different agent B without that evaluator
    agent_b_id, _ = _init_agent(client)

    # When: assigning policy to agent B
    resp = client.post(f"/api/v1/agents/{agent_b_id}/policy/{policy_id}")

    # Then: incompatible controls error
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "POLICY_CONTROL_INCOMPATIBLE"


def test_init_agent_rejects_builtin_evaluator_name(client: TestClient) -> None:
    # Given: a payload that registers an evaluator matching a built-in name
    payload = {
        "agent": {
            "agent_name": str(uuid.uuid4()),
            "agent_name": f"agent-{uuid.uuid4().hex[:12]}",
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": [],
        "evaluators": [
            {"name": "regex", "description": "conflict", "config_schema": {}},
        ],
    }

    # When: initializing the agent
    resp = client.post("/api/v1/agents/initAgent", json=payload)

    # Then: conflict is returned
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "EVALUATOR_NAME_CONFLICT"


def test_init_agent_same_name_is_idempotent(client: TestClient) -> None:
    # Given: an existing agent with a specific name
    name = f"agent-{uuid.uuid4().hex[:12]}"
    _init_agent(client, agent_name=name)

    # When: re-registering with the same name
    payload = {
        "agent": {
            "agent_name": name,
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": [],
    }
    resp = client.post("/api/v1/agents/initAgent", json=payload)

    # Then: request is idempotent
    assert resp.status_code == 200
    assert resp.json()["created"] is False


def test_init_agent_different_name_creates_new_agent(client: TestClient) -> None:
    # Given: an existing agent
    original_name = f"agent-{uuid.uuid4().hex[:12]}"
    _init_agent(client, agent_name=original_name)

    # When: registering another agent with a different name
    payload = {
        "agent": {
            "agent_name": f"{original_name}-renamed",
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": [],
    }
    resp = client.post("/api/v1/agents/initAgent", json=payload)

    # Then: a new agent is created
    assert resp.status_code == 200
    assert resp.json()["created"] is True


def test_list_agent_controls_corrupted_control_data_returns_422(
    client: TestClient,
) -> None:
    # Given: an agent with a policy that includes a control
    agent_name, _ = _init_agent(client)
    control_payload = deepcopy(VALID_CONTROL_PAYLOAD)
    control_payload["condition"]["evaluator"] = {"name": "regex", "config": {"pattern": "x"}}
    control_id = _create_control_with_data(client, control_payload)
    policy_id = _create_policy(client)
    assoc = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    assert assoc.status_code == 200
    assign = client.post(f"/api/v1/agents/{agent_name}/policy/{policy_id}")
    assert assign.status_code == 200

    # And: the control data is corrupted in the DB
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE controls SET data = CAST(:data AS JSONB) WHERE id = :id"),
            {"data": "{\"bad\": \"data\"}", "id": control_id},
        )

    # When: listing agent controls
    resp = client.get(f"/api/v1/agents/{agent_name}/controls")

    # Then: corrupted data error is returned
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "CORRUPTED_DATA"


def test_list_agent_controls_corrupted_unrendered_control_data_returns_422(
    client: TestClient,
) -> None:
    # Given: an agent with a directly associated unrendered template control
    agent_name, _ = _init_agent(client)
    control_id = _create_template_control_with_data(client, _unrendered_template_payload())
    assign = client.post(f"/api/v1/agents/{agent_name}/controls/{control_id}")
    assert assign.status_code == 200

    # And: the unrendered template data becomes corrupted in the DB
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE controls SET data = CAST(:data AS JSONB) WHERE id = :id"),
            {"data": "{\"template\": {\"description\": \"bad\"}}", "id": control_id},
        )

    # When: listing agent controls with the default active-only view
    resp = client.get(f"/api/v1/agents/{agent_name}/controls")

    # Then: the excluded-by-default corrupted row still fails fast
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "CORRUPTED_DATA"


def test_list_agents_invalid_cursor_returns_first_page(client: TestClient) -> None:
    # Given: two agents
    _init_agent(client, agent_name=f"agent-{uuid.uuid4().hex[:12]}")
    _init_agent(client, agent_name=f"agent-{uuid.uuid4().hex[:12]}")

    # When: listing agents without cursor
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    base = resp.json()

    # When: listing agents with an invalid cursor
    resp2 = client.get("/api/v1/agents", params={"cursor": "not-a-uuid"})
    assert resp2.status_code == 200
    with_cursor = resp2.json()

    # Then: results match the first page
    assert with_cursor["agents"] == base["agents"]
    assert with_cursor["pagination"]["total"] == base["pagination"]["total"]


def test_list_agent_evaluators_corrupted_data_returns_empty(client: TestClient) -> None:
    # Given: an agent with corrupted stored data
    agent_name, _ = _init_agent(client, evaluators=[{"name": "eval-a", "config_schema": {}}])
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE agents SET data = CAST(:data AS JSONB) WHERE name = :id"),
            {"data": "{\"bad\": \"data\"}", "id": agent_name},
        )

    # When: listing evaluator schemas
    resp = client.get(f"/api/v1/agents/{agent_name}/evaluators")

    # Then: empty list is returned
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluators"] == []
    assert body["pagination"]["total"] == 0


def test_set_agent_policy_rejects_corrupted_agent_data(client: TestClient) -> None:
    # Given: an agent with corrupted stored data and a policy with a control
    agent_name, _ = _init_agent(client)
    policy_id = _create_policy(client)
    control_id = _create_control_with_data(client, VALID_CONTROL_PAYLOAD)
    assoc = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    assert assoc.status_code == 200

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE agents SET data = CAST(:data AS JSONB) WHERE name = :id"),
            {"data": json.dumps({"bad": "data"}), "id": agent_name},
        )

    # When: assigning policy to the agent
    resp = client.post(f"/api/v1/agents/{agent_name}/policy/{policy_id}")

    # Then: incompatible controls error is returned
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "POLICY_CONTROL_INCOMPATIBLE"
    assert any("corrupted data" in err.get("message", "").lower() for err in body.get("errors", []))


def test_set_agent_policy_rejects_missing_agent_evaluator(client: TestClient) -> None:
    # Given: an agent with no evaluators and a control referencing a missing evaluator
    agent_name, agent_name = _init_agent(client)
    policy_id = _create_policy(client)
    control_id = _create_control_with_data(client, VALID_CONTROL_PAYLOAD)
    assoc = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    assert assoc.status_code == 200

    with engine.begin() as conn:
        corrupted_payload = deepcopy(VALID_CONTROL_PAYLOAD)
        corrupted_payload["condition"]["evaluator"] = {
            "name": f"{agent_name}:missing",
            "config": {},
        }
        conn.execute(
            text("UPDATE controls SET data = CAST(:data AS JSONB) WHERE id = :id"),
            {
                "data": json.dumps(corrupted_payload),
                "id": control_id,
            },
        )

    # When: assigning policy to the agent
    resp = client.post(f"/api/v1/agents/{agent_name}/policy/{policy_id}")

    # Then: incompatible controls error is returned
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "POLICY_CONTROL_INCOMPATIBLE"
    assert any("not registered" in err.get("message", "").lower() for err in body.get("errors", []))


def test_set_agent_policy_rejects_invalid_agent_evaluator_config(client: TestClient) -> None:
    # Given: an agent with an evaluator schema requiring \"pattern\"
    agent_name, agent_name = _init_agent(
        client,
        evaluators=[
            {
                "name": "custom",
                "description": "custom",
                "config_schema": {
                    "type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"],
                },
            }
        ],
    )
    policy_id = _create_policy(client)
