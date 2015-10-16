"""Policy management operations for Agent Control SDK."""

from typing import Any, cast

from .client import AgentControlClient
from .validation import ensure_agent_name


async def create_policy(
    client: AgentControlClient,
    name: str
) -> dict[str, Any]:
    """
    Create a new policy with a unique name.

    Policies group controls together and can be assigned to agents.
    A newly created policy has no controls until they are explicitly added.

    Args:
        client: AgentControlClient instance
        name: Unique name for the policy

    Returns:
        Dictionary containing:
            - policy_id: ID of the created policy

    Raises:
        httpx.HTTPError: If request fails
        HTTPException 409: Policy with this name already exists
        HTTPException 500: Database error during creation

    Example:
        async with AgentControlClient() as client:
            result = await create_policy(client, "production-policy")
            policy_id = result["policy_id"]
            print(f"Created policy with ID: {policy_id}")
    """
    response = await client.http_client.put(
        "/api/v1/policies",
        json={"name": name}
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def add_control_to_policy(
    client: AgentControlClient,
    policy_id: int,
    control_id: int
) -> dict[str, Any]:
    """
    Associate a control with a policy.

    This operation is idempotent - adding the same control multiple times has no effect.
    Agents with this policy will immediately see the added control.

    Args:
        client: AgentControlClient instance
        policy_id: ID of the policy
        control_id: ID of the control to add

    Returns:
        Dictionary containing:
            - success: True if operation succeeded

    Raises:
        httpx.HTTPError: If request fails
        HTTPException 404: Policy or control not found
        HTTPException 500: Database error

    Example:
        async with AgentControlClient() as client:
