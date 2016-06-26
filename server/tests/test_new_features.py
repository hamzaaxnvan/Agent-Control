"""Tests for new features: evaluators endpoint, policy validation, PATCH agents."""

import uuid

from fastapi.testclient import TestClient

from .utils import canonicalize_control_payload


def make_agent_payload(
    agent_name: str | None = None,
    name: str | None = None,
    steps: list | None = None,
    evaluators: list | None = None,
):
    """Helper to create agent payload."""
    if agent_name is not None:
        name = agent_name
    elif name is None:
        name = f"agent-{uuid.uuid4().hex[:12]}"
    canonical_name = name.lower().replace(" ", "-")
    if len(canonical_name) < 10:
        canonical_name = f"{canonical_name}-agent".replace("--", "-")
    return {
        "agent": {
            "agent_name": canonical_name,
            "agent_name": canonical_name,
            "agent_description": "desc",
            "agent_version": "1.0",
        },
        "steps": steps or [],
        "evaluators": evaluators or [],
    }


# =============================================================================
# GET /evaluators endpoint
# =============================================================================


def test_get_evaluators(client: TestClient) -> None:
    """Given built-in evaluators are registered, when listing evaluators, then returns all with schemas."""
    # Given: built-in evaluators are registered
    # When: listing evaluators
    resp = client.get("/api/v1/evaluators")

    # Then: response includes built-in evaluators with schemas
    assert resp.status_code == 200
    evaluators = resp.json()
    assert isinstance(evaluators, dict)
    assert "regex" in evaluators
    assert "list" in evaluators

    regex = evaluators["regex"]
    assert regex["name"] == "regex"
    assert "version" in regex
    assert "description" in regex
    assert "config_schema" in regex
    assert isinstance(regex["config_schema"], dict)


def test_get_evaluators_schema_has_properties(client: TestClient) -> None:
    """Given the regex evaluator is registered, when listing evaluators, then schema has pattern property."""
    # Given: the regex evaluator is registered
    # When: listing evaluators
    resp = client.get("/api/v1/evaluators")

    # Then: regex schema includes expected properties
    assert resp.status_code == 200
    evaluators = resp.json()
    regex_schema = evaluators["regex"]["config_schema"]
    assert "properties" in regex_schema
    assert "pattern" in regex_schema["properties"]


# =============================================================================
# PATCH /agents endpoint
# =============================================================================


def test_patch_agent_remove_step(client: TestClient) -> None:
    """Given an agent with multiple steps, when removing one step, then only that step is removed."""
    # Given:
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload = make_agent_payload(
        agent_name=agent_name,
        name=name,
        steps=[
            {"type": "tool", "name": "tool1", "input_schema": {}, "output_schema": {}},
            {"type": "tool", "name": "tool2", "input_schema": {}, "output_schema": {}},
        ],
    )
    client.post("/api/v1/agents/initAgent", json=payload)

    # When:
    patch_resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={"remove_steps": [{"type": "tool", "name": "tool1"}]},
    )

    # Then:
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["steps_removed"] == [{"type": "tool", "name": "tool1"}]
    assert data["evaluators_removed"] == []

    get_resp = client.get(f"/api/v1/agents/{agent_name}")
    steps = [s["name"] for s in get_resp.json()["steps"]]
    assert "tool1" not in steps
    assert "tool2" in steps


def test_patch_agent_remove_evaluator(client: TestClient) -> None:
    """Given an agent with multiple evaluators, when removing one, then only that evaluator is removed."""
    # Given:
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload = make_agent_payload(
        agent_name=agent_name,
        name=name,
        evaluators=[
            {"name": "eval1", "config_schema": {}},
            {"name": "eval2", "config_schema": {}},
        ],
    )
    client.post("/api/v1/agents/initAgent", json=payload)

    # When:
    patch_resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={"remove_evaluators": ["eval1"]},
    )

    # Then:
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["evaluators_removed"] == ["eval1"]

    get_resp = client.get(f"/api/v1/agents/{agent_name}/evaluators")
    evals = [e["name"] for e in get_resp.json()["evaluators"]]
    assert "eval1" not in evals
    assert "eval2" in evals


def test_patch_agent_remove_nonexistent_is_idempotent(client: TestClient) -> None:
    """Given an agent, when removing nonexistent items, then succeeds with empty removed lists."""
    # Given:
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload = make_agent_payload(agent_name=agent_name, name=name)
    client.post("/api/v1/agents/initAgent", json=payload)

    # When:
    patch_resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={
            "remove_steps": [{"type": "tool", "name": "nonexistent"}],
            "remove_evaluators": ["also_nonexistent"],
        },
    )

    # Then:
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["steps_removed"] == []
    assert data["evaluators_removed"] == []


def test_patch_agent_not_found(client: TestClient) -> None:
    """Given a nonexistent agent UUID, when patching, then returns 404."""
    # Given:
    fake_id = str(uuid.uuid4())

    # When:
    patch_resp = client.patch(
        f"/api/v1/agents/{fake_id}",
        json={"remove_steps": [{"type": "tool", "name": "tool1"}]},
    )

    # Then:
    assert patch_resp.status_code == 404


def test_patch_agent_remove_both(client: TestClient) -> None:
    """Given an agent with steps and evaluators, when removing both, then both are removed."""
    # Given:
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload = make_agent_payload(
        agent_name=agent_name,
        name=name,
        steps=[{"type": "tool", "name": "my_tool", "input_schema": {}, "output_schema": {}}],
        evaluators=[{"name": "my_eval", "config_schema": {}}],
    )
    client.post("/api/v1/agents/initAgent", json=payload)

    # When:
    patch_resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={
            "remove_steps": [{"type": "tool", "name": "my_tool"}],
            "remove_evaluators": ["my_eval"],
        },
    )

    # Then:
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["steps_removed"] == [{"type": "tool", "name": "my_tool"}]
    assert data["evaluators_removed"] == ["my_eval"]


def test_patch_agent_empty_request_is_noop(client: TestClient) -> None:
    """Given an agent, when patching with empty lists, then nothing changes and succeeds."""
    # Given:
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload = make_agent_payload(
        agent_name=agent_name,
        name=name,
        steps=[{"type": "tool", "name": "keep_me", "input_schema": {}, "output_schema": {}}],
        evaluators=[{"name": "keep_me_too", "config_schema": {}}],
    )
    client.post("/api/v1/agents/initAgent", json=payload)

    # When:
    patch_resp = client.patch(
        f"/api/v1/agents/{agent_name}",
        json={"remove_steps": [], "remove_evaluators": []},
    )

    # Then:
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["steps_removed"] == []
    assert data["evaluators_removed"] == []

    # Verify nothing was removed
    get_resp = client.get(f"/api/v1/agents/{agent_name}")
    steps = [s["name"] for s in get_resp.json()["steps"]]
    assert "keep_me" in steps

    get_evals = client.get(f"/api/v1/agents/{agent_name}/evaluators")
    evals = [e["name"] for e in get_evals.json()["evaluators"]]
    assert "keep_me_too" in evals


# =============================================================================
# Policy assignment validation
# =============================================================================


def _create_policy_with_control(
    client: TestClient, policy_name: str, control_name: str, control_data: dict
) -> tuple[int, int]:
    """Helper to create a policy with a control.

    Returns (policy_id, control_id).
    """
    # Create policy
    pol_resp = client.put("/api/v1/policies", json={"name": policy_name})
    assert pol_resp.status_code == 200
    policy_id = pol_resp.json()["policy_id"]

    # Create control
    ctl_resp = client.put(
        "/api/v1/controls",
        json={"name": control_name, "data": canonicalize_control_payload(control_data)},
    )
    assert ctl_resp.status_code == 200
    control_id = ctl_resp.json()["control_id"]

    # Add control to policy
    client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")

    return policy_id, control_id


def test_policy_assignment_with_builtin_evaluator(client: TestClient) -> None:
    """Given an agent and a policy with built-in evaluator control, when assigning policy, then succeeds."""
    # Given:
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload = make_agent_payload(agent_name=agent_name, name=name)
    client.post("/api/v1/agents/initAgent", json=payload)

    policy_id, _ = _create_policy_with_control(
        client,
        f"policy-{uuid.uuid4().hex[:8]}",
        f"control-{uuid.uuid4().hex[:8]}",
        {
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["pre"]},
            "selector": {"path": "input"},
            "evaluator": {"name": "regex", "config": {"pattern": "test.*"}},
            "action": {"decision": "deny"},
        },
    )

    # When:
    resp = client.post(f"/api/v1/agents/{agent_name}/policy/{policy_id}")

    # Then:
