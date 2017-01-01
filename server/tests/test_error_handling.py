"""Tests for database error handling and rollback scenarios."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from agent_control_server.db import get_async_db

from .utils import VALID_CONTROL_PAYLOAD


async def mock_db_with_commit_failure() -> AsyncGenerator[AsyncSession, None]:
    """Mock database session that fails on commit."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.commit.side_effect = Exception("Database error")
    
    # Mock execute to return an awaitable that resolves to a result with scalars/first
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_result.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    
    yield mock_session


def test_init_agent_rollback_on_create_failure(
    app: FastAPI, client: TestClient
) -> None:
    """Test that init_agent rolls back transaction when commit fails on create."""
    # Given: a valid agent init payload
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    agent_name = agent_name
    payload = {
        "agent": {
            "agent_name": agent_name,
            "agent_name": agent_name,
            "agent_description": "test",
            "agent_version": "1.0",
            "agent_metadata": {},
        },
        "steps": [],
    }

    # When: commit fails during agent creation
    app.dependency_overrides[get_async_db] = mock_db_with_commit_failure
    try:
        resp = client.post("/api/v1/agents/initAgent", json=payload)

        # Then: rollback is called and 500 error is returned
        assert resp.status_code == 500
        assert "database error" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_delete_agent_policy_rollback_on_failure(
    app: FastAPI, client: TestClient, db_engine: object
) -> None:
    """Test that delete_agent_policy rolls back when commit fails."""
    # Given: an agent with an assigned policy
    agent_payload = {
        "agent": {
            "agent_name": str(uuid.uuid4()),
            "agent_name": f"test-agent-{uuid.uuid4()}",
            "agent_description": "test",
            "agent_version": "1.0",
            "agent_metadata": {},
        },
        "steps": [],
    }
    r1 = client.post("/api/v1/agents/initAgent", json=agent_payload)
    assert r1.status_code == 200
    agent_name = agent_payload["agent"]["agent_name"]

    policy_name = f"test-policy-{uuid.uuid4()}"
    r2 = client.put("/api/v1/policies", json={"name": policy_name})
    assert r2.status_code == 200
    policy_id = r2.json()["policy_id"]

    assign_resp = client.post(f"/api/v1/agents/{agent_name}/policy/{policy_id}")
    assert assign_resp.status_code == 200

    # And: a database session that fails on commit
    from agent_control_server.models import Agent
    from sqlalchemy.orm import Session

    with Session(db_engine) as session:
        existing_agent = (
            session.query(Agent).filter(Agent.name == agent_name).first()
        )
        assert existing_agent is not None

        async def mock_db_for_delete_policy() -> AsyncGenerator[AsyncSession, None]:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.commit.side_effect = Exception("Database error")

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = existing_agent
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.rollback = AsyncMock()
            yield mock_session

        # When: deleting policy and commit fails
        app.dependency_overrides[get_async_db] = mock_db_for_delete_policy
        try:
            resp = client.delete(f"/api/v1/agents/{agent_name}/policy")
        finally:
            app.dependency_overrides.clear()

        # Then: rollback is called and 500 error is returned
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "DATABASE_ERROR"


def test_init_agent_rollback_on_update_failure(
    app: FastAPI, client: TestClient, db_engine: object
) -> None:
    """Test that init_agent rolls back transaction when commit fails on update."""
    # Given: an existing agent
    agent_name = f"agent-{uuid.uuid4().hex[:12]}"
    agent_name = agent_name
    payload = {
        "agent": {
            "agent_name": agent_name,
            "agent_name": agent_name,
            "agent_description": "test",
            "agent_version": "1.0",
            "agent_metadata": {},
        },
        "steps": [
            {
                "type": "tool",
                "name": "tool_a",
                "input_schema": {"a": "int"},
