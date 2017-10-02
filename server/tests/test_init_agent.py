import logging
import uuid
from typing import Any

from agent_control_server.config import db_config
from agent_control_server.models import Agent
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Create sync engine for raw database queries in tests
engine = create_engine(db_config.get_url(), echo=False)


def _collect_route_paths(routes: list[Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(f"{prefix}{path}")
            continue

        include_context = getattr(route, "include_context", None)
        included_router = getattr(include_context, "included_router", None)
        if included_router is None:
            continue

        include_prefix = getattr(include_context, "prefix", "")
        paths.update(
            _collect_route_paths(
                list(getattr(included_router, "routes", [])),
                f"{prefix}{include_prefix}",
            )
        )
    return paths


def make_agent_payload(
    agent_name: str | None = None,
    name: str = "testagent0001",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_name = (
        name if name != "testagent0001" else (agent_name or f"agent-{uuid.uuid4().hex[:12]}")
    )
    canonical_name = resolved_name.lower().replace(" ", "-")
    if len(canonical_name) < 10:
        canonical_name = f"{canonical_name}-agent".replace("--", "-")
    if steps is None:
        steps = [
            {
                "type": "tool",
                "name": "tool_a",
                "input_schema": {"a": "int"},
                "output_schema": {"ok": "bool"},
            }
        ]
    return {
        "agent": {
            "agent_name": canonical_name,
            "agent_description": "desc",
            "agent_version": "1.0",
            "agent_metadata": {"env": "test"},
        },
        "steps": steps,
    }


def _collect_paths(routes: list, prefix: str = "") -> set[str]:
    """Recursively collect route paths, handling FastAPI's _IncludedRouter wrapper."""
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(prefix + path)
        nested = getattr(route, "original_router", None)
        if nested:
            ctx = getattr(route, "include_context", None)
            pfx = getattr(ctx, "prefix", "") if ctx else ""
            paths |= _collect_paths(nested.routes, prefix + pfx)
    return paths


def test_init_agent_route_exists(app: FastAPI) -> None:
    # Given: an application router
    paths = _collect_route_paths(list(app.router.routes))
    # When: inspecting registered paths
    # (computation done above to gather all paths)
    # Then: initAgent and agent retrieval endpoints are present
    assert "/api/v1/agents/initAgent" in paths
    assert "/api/v1/agents/{agent_name}" in paths


def test_agent_routes_are_registered(client: TestClient) -> None:
    # Given: malformed requests that should still match registered agent routes
    # When: calling initAgent without the required body fields
    init_resp = client.post("/api/v1/agents/initAgent", json={})

    # And: using an unsupported method on the agent resource route
    agent_resp = client.post("/api/v1/agents/some-agent")

    # Then: routing reached the expected endpoints instead of falling through to 404
    assert init_resp.status_code == 422
    assert agent_resp.status_code == 405


def test_init_agent_creates_and_gets_agent(client: TestClient) -> None:
    # Given: an init payload
    payload = make_agent_payload()
    # When: initializing the agent
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # Then: the agent is created and controls are empty
    assert body["created"] is True
    assert body["controls"] == []

    agent_name = payload["agent"]["agent_name"]
    # When: retrieving the agent by id
    resp2 = client.get(f"/api/v1/agents/{agent_name}")
    assert resp2.status_code == 200
    data = resp2.json()
    # Then: stored agent fields match the request
    assert data["agent"]["agent_name"] == payload["agent"]["agent_name"]
    assert {s["name"] for s in data["steps"]} == {payload["steps"][0]["name"]}


def test_agent_endpoints_normalize_mixed_case_agent_name(client: TestClient) -> None:
    # Given: an agent registered with mixed-case identifier
    mixed_case_name = "Agent-PathNorm01"
    payload = {
        "agent": {
            "agent_name": mixed_case_name,
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": [],
    }
    init_resp = client.post("/api/v1/agents/initAgent", json=payload)
    assert init_resp.status_code == 200

    # When: hitting path-based agent endpoints using mixed-case path params
    get_resp = client.get(f"/api/v1/agents/{mixed_case_name}")
    assert get_resp.status_code == 200
    assert get_resp.json()["agent"]["agent_name"] == mixed_case_name.lower()

    policy_id = _create_policy(client)
    set_policy_resp = client.post(f"/api/v1/agents/{mixed_case_name}/policy/{policy_id}")
    assert set_policy_resp.status_code == 200

    get_policy_resp = client.get(f"/api/v1/agents/{mixed_case_name}/policy")
    assert get_policy_resp.status_code == 200
    assert get_policy_resp.json()["policy_id"] == policy_id

    controls_resp = client.get(f"/api/v1/agents/{mixed_case_name}/controls")
    assert controls_resp.status_code == 200

    evaluators_resp = client.get(f"/api/v1/agents/{mixed_case_name}/evaluators")
    assert evaluators_resp.status_code == 200

    patch_resp = client.patch(
        f"/api/v1/agents/{mixed_case_name}",
        json={"remove_steps": [], "remove_evaluators": []},
    )
    assert patch_resp.status_code == 200

    delete_policy_resp = client.delete(f"/api/v1/agents/{mixed_case_name}/policy")
    assert delete_policy_resp.status_code == 200


def test_init_agent_nameempotent_same_steps(client: TestClient) -> None:
    # Given: an init payload
    payload = make_agent_payload()
    # When: initializing the agent the first time
    r1 = client.post("/api/v1/agents/initAgent", json=payload)
    assert r1.status_code == 200
    # Then: it is created
    assert r1.json()["created"] is True

    # When: initializing the same payload again
    r2 = client.post("/api/v1/agents/initAgent", json=payload)
    assert r2.status_code == 200
    # Then: it is not created again (idempotent)
    assert r2.json()["created"] is False


def test_init_agent_updates_metadata_on_reinit(client: TestClient) -> None:
    """Test that agent metadata is refreshed on re-registration.

    Given: An existing agent with initial metadata
    When: Re-initializing with updated description/version
    Then: The new metadata is persisted
    """
    # Given: create initial agent
    agent_name = "metadatatestagent"
    initial_payload = {
        "agent": {
            "agent_name": agent_name,
            "agent_description": "Original description",
            "agent_version": "1.0.0",
            "agent_metadata": {"env": "dev"},
        },
        "steps": [],
    }
    r1 = client.post("/api/v1/agents/initAgent", json=initial_payload)
    assert r1.status_code == 200
    assert r1.json()["created"] is True

    # When: re-init with updated metadata
    updated_payload = {
        "agent": {
            "agent_name": agent_name,
            "agent_description": "Updated description",
            "agent_version": "2.0.0",
            "agent_metadata": {"env": "prod", "new_field": "value"},
        },
        "steps": [],
    }
    r2 = client.post("/api/v1/agents/initAgent", json=updated_payload)
    assert r2.status_code == 200
    assert r2.json()["created"] is False

    # Then: verify metadata is updated
    get_resp = client.get(f"/api/v1/agents/{agent_name}")
    assert get_resp.status_code == 200
    agent_data = get_resp.json()["agent"]
    assert agent_data["agent_description"] == "Updated description"
    assert agent_data["agent_version"] == "2.0.0"
    assert agent_data["agent_metadata"] == {"env": "prod", "new_field": "value"}


def test_init_agent_adds_new_step(client: TestClient) -> None:
    # Given: an agent id and base payload
    agent_name = str(uuid.uuid4())
    base = make_agent_payload(agent_name=agent_name)
    # When: initializing the agent
    r1 = client.post("/api/v1/agents/initAgent", json=base)
    assert r1.status_code == 200

    # When: sending an additional step
    steps = base["steps"] + [
        {
            "type": "tool",
            "name": "tool_b",
            "input_schema": {"b": "str"},
            "output_schema": {"ok": "bool"},
        }
    ]
    r2 = client.post(
        "/api/v1/agents/initAgent",
        json=make_agent_payload(agent_name=agent_name, steps=steps),
    )
    assert r2.status_code == 200
    # Then: the agent is not newly created
    assert r2.json()["created"] is False

    # When: fetching the agent
    g = client.get(f"/api/v1/agents/{agent_name}")
    assert g.status_code == 200
    names = {s["name"] for s in g.json()["steps"]}
    # Then: both steps are present
    assert names == {"tool_a", "tool_b"}


def test_init_agent_overwrites_step_on_signature_change(client: TestClient) -> None:
    # Given: a base payload for an agent
    agent_name = str(uuid.uuid4())
    base = make_agent_payload(agent_name=agent_name)
    # When: initializing the agent
    r1 = client.post("/api/v1/agents/initAgent", json=base)
    assert r1.status_code == 200

    # When: updating tool_a schema
    changed = make_agent_payload(
        agent_name=agent_name,
        steps=[
            {
                "type": "tool",
                "name": "tool_a",
                "input_schema": {"a": "str"},  # changed type
                "output_schema": {"ok": "bool"},
            }
        ],
    )
    r2 = client.post("/api/v1/agents/initAgent", json=changed)
    # Then: schema conflict error is returned (schema changes are now rejected)
    assert r2.status_code == 409
    body = r2.json()
    assert body["error_code"] == "SCHEMA_INCOMPATIBLE"
    assert "schema conflict" in body["detail"].lower()


def test_get_agent_returns_evaluators(client: TestClient) -> None:
    """Test that GET /agents/{id} returns evaluators."""
    # Given: an agent with evaluators
    agent_name = str(uuid.uuid4())
    payload = make_agent_payload(agent_name=agent_name)
    payload["evaluators"] = [
        {"name": "eval-a", "description": "First", "config_schema": {}},
        {"name": "eval-b", "description": "Second", "config_schema": {"type": "object"}},
    ]
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    assert resp.status_code == 200

    # When: fetching the agent
    get_resp = client.get(f"/api/v1/agents/{agent_name}")
    # Then: evaluators are included in the response
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "evaluators" in data
    assert len(data["evaluators"]) == 2
    names = {e["name"] for e in data["evaluators"]}
    assert names == {"eval-a", "eval-b"}


def test_get_agent_not_found(client: TestClient) -> None:
    # Given: a random (missing) agent id
    missing = str(uuid.uuid4())
    # When: fetching the agent
    resp = client.get(f"/api/v1/agents/{missing}")
    # Then: a 404 is returned
    assert resp.status_code == 404


def test_init_agent_logs_warning_on_bad_existing_data(client: TestClient, caplog) -> None:
    # Given: an existing agent
    payload = make_agent_payload()
    r1 = client.post("/api/v1/agents/initAgent", json=payload)
    assert r1.status_code == 200

    # When: corrupting the stored data so parsing fails
    with Session(engine) as session:
        agent = session.execute(
            select(Agent).where(Agent.name == payload["agent"]["agent_name"])
        ).scalar_one()
        agent.data = {"foo": "bar"}
        session.commit()

    # When: re-initializing with the same payload (without force_replace)
    logger_name = "agent_control_server.endpoints.agents"
    with caplog.at_level(logging.ERROR, logger=logger_name):
        r2 = client.post("/api/v1/agents/initAgent", json=payload)
        # Then: a 422 error is returned (RFC 7807 format)
        assert r2.status_code == 422
        response_data = r2.json()
        assert "corrupted data" in response_data.get("detail", "").lower()
        # Check hint contains force_replace suggestion
        assert "force_replace" in response_data.get("hint", "").lower()
        assert response_data["errors"][0]["message"] == (
            "Stored agent data is corrupted and cannot be parsed."
