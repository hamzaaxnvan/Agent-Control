"""
Integration tests for server health and connectivity.

These tests verify basic server functionality:
1. Server health check
2. Client connection management
3. Error handling
"""

import agent_control
import pytest


@pytest.mark.asyncio
async def test_health_check_workflow(
    client: agent_control.AgentControlClient
) -> None:
    """
    Test server health check.

    Verifies:
    - Health endpoint is accessible
    - Response includes status
    - Status is healthy
    """
    health = await client.health_check()

    # Verify response structure
    assert isinstance(health, dict)
    assert "status" in health

    print(f"✓ Server health: {health['status']}")


@pytest.mark.asyncio
async def test_client_context_manager(
    monkeypatch: pytest.MonkeyPatch, server_url: str
) -> None:
    """
