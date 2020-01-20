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
