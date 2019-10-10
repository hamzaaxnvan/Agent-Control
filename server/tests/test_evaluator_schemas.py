"""Tests for evaluator schema functionality."""

import uuid

import pytest
from fastapi.testclient import TestClient

from agent_control_server.services.schema_compat import check_schema_compatibility


def make_agent_payload(
    agent_name: str | None = None,
    name: str | None = None,
    evaluators: list | None = None,
):
    """Helper to create agent payload with evaluators."""
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
        "steps": [],
        "evaluators": evaluators or [],
    }


# =============================================================================
# initAgent with evaluators
# =============================================================================


def test_init_agent_with_evaluators(client: TestClient) -> None:
    """Test creating agent with evaluator schemas."""
    # Given: A payload with custom evaluator
    payload = make_agent_payload(
        evaluators=[
            {
                "name": "my-custom-eval",
                "description": "A custom evaluator",
                "config_schema": {
                    "type": "object",
                    "properties": {"threshold": {"type": "number"}},
                },
            }
        ]
    )
    # When: Initializing agent
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    # Then: Agent created successfully
    assert resp.status_code == 200
    assert resp.json()["created"] is True


def test_init_agent_evaluator_name_collision_rejected(client: TestClient) -> None:
    """Test that evaluator names conflicting with built-in evaluators are rejected."""
    # Given: Evaluator name conflicting with built-in
    payload = make_agent_payload(
        evaluators=[
            {
                "name": "regex",  # Conflicts with built-in
                "description": "Trying to override regex",
                "config_schema": {},
            }
        ]
    )
    # When: Initializing agent
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    # Then: Should be rejected (RFC 7807 format)
    assert resp.status_code == 409
    response_data = resp.json()
    assert "conflicts with built-in evaluator" in response_data.get("detail", "")


def test_init_agent_evaluator_name_collision_list(client: TestClient) -> None:
    """Test that 'list' built-in name is also rejected."""
    # Given: Evaluator named 'list'
    payload = make_agent_payload(
        evaluators=[{"name": "list", "config_schema": {}}]
    )
    # When: Initializing agent
    resp = client.post("/api/v1/agents/initAgent", json=payload)
    # Then: Should be rejected (RFC 7807 format - ConflictError returns 409)
    assert resp.status_code == 409


def test_init_agent_update_evaluator_compatible_schema(client: TestClient) -> None:
    """Test updating evaluator with compatible schema change (add optional field)."""
    # Given: Agent with evaluator
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload1 = make_agent_payload(
        agent_name=agent_name,
        name=name,
        evaluators=[
            {
                "name": "my-eval",
                "config_schema": {
                    "type": "object",
                    "properties": {"threshold": {"type": "number"}},
                    "required": ["threshold"],
                },
            }
        ],
    )
    resp1 = client.post("/api/v1/agents/initAgent", json=payload1)
    assert resp1.status_code == 200

    # When: Updating with compatible schema (add optional field)
    payload2 = make_agent_payload(
        agent_name=agent_name,
        name=name,
        evaluators=[
            {
                "name": "my-eval",
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "number"},
                        "max_retries": {"type": "integer"},  # New optional
                    },
                    "required": ["threshold"],
                },
            }
        ],
    )
    resp2 = client.post("/api/v1/agents/initAgent", json=payload2)
    # Then: Should be accepted
    assert resp2.status_code == 200


def test_init_agent_update_evaluator_incompatible_schema_rejected(
    client: TestClient,
) -> None:
    """Test that incompatible schema change is rejected."""
    # Given: Agent with evaluator
    agent_name = str(uuid.uuid4())
    name = f"Test Agent {uuid.uuid4().hex[:8]}"
    payload1 = make_agent_payload(
        agent_name=agent_name,
        name=name,
        evaluators=[
            {
                "name": "my-eval",
                "config_schema": {
                    "type": "object",
                    "properties": {"threshold": {"type": "number"}},
                },
            }
        ],
    )
    resp1 = client.post("/api/v1/agents/initAgent", json=payload1)
    assert resp1.status_code == 200

    # When: Updating with incompatible schema (remove property)
    payload2 = make_agent_payload(
        agent_name=agent_name,
        name=name,
        evaluators=[
            {
                "name": "my-eval",
                "config_schema": {
                    "type": "object",
                    "properties": {},  # Removed threshold
                },
            }
        ],
    )
    resp2 = client.post("/api/v1/agents/initAgent", json=payload2)
