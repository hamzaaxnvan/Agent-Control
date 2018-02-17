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

    # Verify it's a 409 conflict error
    assert "409" in str(exc_info.value)
    print("✓ Duplicate policy name correctly rejected")


@pytest.mark.asyncio
async def test_control_association_workflow(
    client: agent_control.AgentControlClient,
    test_policy: dict,
    test_control: dict
) -> None:
    """
    Test adding and removing controls from policies.

    Verifies:
    - Control can be added to policy
    - Operation is idempotent (adding twice works)
    - Control can be removed from policy
    - Removal is idempotent
    """
    policy_id = test_policy["policy_id"]
    control_id = test_control["control_id"]

    # Add control to policy
    result = await agent_control.policies.add_control_to_policy(
        client,
        policy_id,
        control_id
    )

    assert result["success"] is True
    print(f"✓ Control {control_id} added to policy {policy_id}")

    # Add again (should be idempotent)
    result = await agent_control.policies.add_control_to_policy(
        client,
        policy_id,
        control_id
    )

    assert result["success"] is True
    print("✓ Idempotent add verified")
