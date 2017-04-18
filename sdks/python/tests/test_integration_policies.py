"""
Integration tests for Policy operations.

These tests verify policy management workflows:
1. Policy creation
2. Adding/removing controls from policies
3. Listing policy controls
"""

import agent_control
import pytest


@pytest.mark.asyncio
async def test_policy_creation_workflow(
    client: agent_control.AgentControlClient,
    unique_name: str
) -> None:
    """
    Test policy creation workflow.

    Verifies:
    - Policy can be created with unique name
    - Response includes policy_id
    - Duplicate names are rejected
    """
    policy_name = f"test-policy-{unique_name}"

    # Create policy
    result = await agent_control.policies.create_policy(client, policy_name)

    # Verify response
    assert "policy_id" in result
    assert isinstance(result["policy_id"], int)

    policy_id = result["policy_id"]
    print(f"✓ Policy created: ID {policy_id}")

    # Try to create duplicate (should fail with 409)
    with pytest.raises(Exception) as exc_info:
        await agent_control.policies.create_policy(client, policy_name)

