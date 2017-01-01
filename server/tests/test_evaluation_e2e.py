"""End-to-end tests for evaluation flow."""
import uuid

from fastapi.testclient import TestClient
from agent_control_models import EvaluationRequest, Step

from .utils import canonicalize_control_payload, create_and_assign_policy


def test_evaluation_flow_deny(client: TestClient):
    # Given: A registered agent with a policy blocking "secret"
    control_data = {
        "description": "Block secret",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {
            "name": "regex",
            "config": {"pattern": "secret"}
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(client, control_data)

    # When: Sending a request containing "secret"
    payload = Step(type="llm", name="test-step", input="This contains a secret", output=None)
    req = EvaluationRequest(
        agent_name=agent_name,
        step=payload,
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req.model_dump(mode="json"))

    # Then: It should be denied
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_safe"] is False
    assert len(data["matches"]) > 0
    assert data["matches"][0]["control_name"] == control_name


def test_evaluation_no_policy(client: TestClient):
    """Test that an agent with no policy assigned is safe."""
    # Given: an agent with no policy assigned
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    client.post("/api/v1/agents/initAgent", json={
        "agent": {"agent_name": agent_name},
        "steps": []
    })

    # When: evaluating content for that agent
    req = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="llm", name="test-step", input="anything", output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req.model_dump(mode="json"))

    # Then: evaluation is safe with no matches
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True
    assert not resp.json()["matches"]


def test_evaluation_accepts_custom_step_type(client: TestClient):
    """The evaluation endpoint accepts custom Step.type values."""
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    client.post(
        "/api/v1/agents/initAgent",
        json={"agent": {"agent_name": agent_name}, "steps": []},
    )

    request = EvaluationRequest(
        agent_name=agent_name,
        step=Step(
            type="retriever",
            name="retrieve-documents",
            input={"query": "anything"},
        ),
        stage="pre",
    )

    response = client.post("/api/v1/evaluation", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    assert response.json()["is_safe"] is True
    assert not response.json()["matches"]


def test_evaluation_empty_policy(client: TestClient):
    """Test that an agent with an empty policy is safe."""
    # Given: an empty policy
    resp = client.put("/api/v1/policies", json={"name": "empty-policy"})
    assert resp.status_code == 200
    policy_id = resp.json()["policy_id"]

    # And: an agent assigned to that policy
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    client.post("/api/v1/agents/initAgent", json={
        "agent": {"agent_name": agent_name},
