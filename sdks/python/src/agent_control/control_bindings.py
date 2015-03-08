"""Control binding management operations for Agent Control SDK."""

from typing import Any, cast

from .client import AgentControlClient


async def upsert_control_binding_by_key(
    client: AgentControlClient,
    *,
    target_type: str,
    target_id: str,
    control_id: int,
    enabled: bool = True,
) -> dict[str, Any]:
    """Attach a control to a target, or update the existing binding."""
    response = await client.http_client.put(
        "/api/v1/control-bindings/by-key",
        json={
            "target_type": target_type,
            "target_id": target_id,
            "control_id": control_id,
            "enabled": enabled,
        },
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def update_control_binding_by_key(
    client: AgentControlClient,
    *,
    target_type: str,
    target_id: str,
