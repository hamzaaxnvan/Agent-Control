"""Agent management operations for Agent Control SDK."""

from typing import Any, Literal, cast

from agent_control_engine import ensure_evaluators_discovered
from agent_control_models import Agent
from agent_control_models.server import AgentControlsResponse

from .client import AgentControlClient
from .validation import ensure_agent_name


def _agent_controls_query_params(
    *,
    rendered_state: Literal["rendered", "unrendered", "all"] | None = None,
    enabled_state: Literal["enabled", "disabled", "all"] | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> dict[str, str] | None:
    """Build optional query params for the agent-controls endpoint."""
    params: dict[str, str] = {}
    if rendered_state is not None:
        params["rendered_state"] = rendered_state
    if enabled_state is not None:
        params["enabled_state"] = enabled_state
    if target_type is not None:
        params["target_type"] = target_type
    if target_id is not None:
        params["target_id"] = target_id
    return params or None


async def register_agent(
    client: AgentControlClient,
    agent: Agent,
    steps: list[dict[str, Any]] | None = None,
    conflict_mode: Literal["strict", "overwrite"] = "overwrite",
    *,
    target_type: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Register an agent with the server via /initAgent endpoint.

    When ``target_type`` and ``target_id`` are both supplied, the server
    merges controls bound to that target into the returned set. The two
    fields must be supplied together.
    """
    ensure_evaluators_discovered()

    if (target_type is None) != (target_id is None):
        raise ValueError(
            "target_type and target_id must be supplied together."
        )

    agent_dict = agent.to_dict()
    agent_dict["agent_name"] = ensure_agent_name(str(agent_dict.get("agent_name", "")))
    payload: dict[str, Any] = {
        "agent": agent_dict,
        "steps": steps or [],
        "conflict_mode": conflict_mode,
    }
    if target_type is not None and target_id is not None:
        payload["target_type"] = target_type
        payload["target_id"] = target_id

    headers = None
    response = await client.http_client.post(
        "/api/v1/agents/initAgent",
        json=payload,
