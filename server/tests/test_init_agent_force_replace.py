"""Tests for force_replace behavior in initAgent endpoint."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_control_server.models import Agent

from .conftest import engine


def test_init_agent_force_replace_default_false_works_normally(client: TestClient):
    """Test that force_replace defaults to false and works normally.

    Given: A new agent
    When: Creating agent without specifying force_replace
    Then: Creates agent normally (force_replace defaults to False)
    """
    # Given: New agent
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    agent_name = agent_name

    # When: Create without force_replace (default)
    resp = client.post("/api/v1/agents/initAgent", json={
        "agent": {
            "agent_name": agent_name,
            "agent_name": agent_name,
            "agent_description": "Test",
            "agent_version": "1.0"
        },
        "steps": []
    })

    # Then: Should succeed
    assert resp.status_code == 200
    assert resp.json()["created"] is True


def test_init_agent_force_replace_false_explicit_works_normally(client: TestClient):
    """Test that explicit force_replace=false works normally.

    Given: A new agent
    When: Creating agent with force_replace=false
    Then: Creates agent normally
    """
    # Given: New agent
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    agent_name = agent_name

    # When: Create with force_replace=false
    resp = client.post("/api/v1/agents/initAgent", json={
        "agent": {
            "agent_name": agent_name,
            "agent_name": agent_name,
            "agent_description": "Test",
            "agent_version": "1.0"
        },
        "steps": [],
        "force_replace": False
    })

    # Then: Should succeed
    assert resp.status_code == 200
    assert resp.json()["created"] is True


def test_init_agent_force_replace_true_on_valid_data_works_normally(client: TestClient):
    """Test that force_replace=true doesn't affect normal updates.

    Given: An existing agent with valid data
    When: Updating with force_replace=true
    Then: Updates normally without data loss
    """
    # Given: Create agent with steps
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    agent_name = agent_name
    
    resp = client.post("/api/v1/agents/initAgent", json={
        "agent": {
            "agent_name": agent_name,
            "agent_name": agent_name,
            "agent_description": "Test",
            "agent_version": "1.0"
        },
        "steps": [
            {"type": "tool", "name": "tool1", "input_schema": {}, "output_schema": {}},
            {"type": "tool", "name": "tool2", "input_schema": {}, "output_schema": {}}
