"""Control management operations for Agent Control SDK."""

from typing import Any, Literal, cast

from agent_control_models import (
    ControlDefinition,
    TemplateControlInput,
    TemplateDefinition,
    TemplateValue,
    UnrenderedTemplateControl,
)

from .client import AgentControlClient


async def list_controls(
    client: AgentControlClient,
    cursor: int | None = None,
    limit: int = 20,
    name: str | None = None,
    enabled: bool | None = None,
    template_backed: bool | None = None,
    cloned: bool | None = None,
    step_type: str | None = None,
    stage: Literal["pre", "post"] | None = None,
    execution: Literal["server", "sdk"] | None = None,
    tag: str | None = None,
    include_attachments: bool = False,
    attachment_target_type: str | None = None,
    attachment_target_id: str | None = None,
) -> dict[str, Any]:
    """
    List all controls with optional filtering and pagination.

    Controls are returned ordered by ID descending (newest first).

    Args:
        client: AgentControlClient instance
        cursor: Control ID to start after (for pagination)
        limit: Maximum number of controls to return (default 20, max 100)
        name: Optional filter by name (partial, case-insensitive match)
        enabled: Optional filter by enabled status
        template_backed: Optional filter by whether the control is template-backed
        cloned: Optional filter by whether the control was cloned from another control
        step_type: Optional filter by step type (built-ins: 'tool', 'llm')
        stage: Optional filter by stage ('pre' or 'post')
        execution: Optional filter by execution ('server' or 'sdk')
        tag: Optional filter by tag
        include_attachments: Whether to include attachment details
        attachment_target_type: Optional target binding type filter for attachments
        attachment_target_id: Optional target binding ID filter for attachments

    Returns:
        Dictionary containing:
            - controls: List of control summaries with id, name, description,
                       enabled, execution, step_types, stages, tags
            - pagination: Object with limit, total, next_cursor, has_more

    Raises:
        httpx.HTTPError: If request fails

    Example:
        async with AgentControlClient() as client:
            # List all controls
            result = await list_controls(client)
            print(f"Total: {result['pagination']['total']}")

            # Filter by type
            llm_controls = await list_controls(client, step_type="llm")

            # Paginate
            page1 = await list_controls(client, limit=10)
            if page1['pagination']['has_more']:
                page2 = await list_controls(
                    client,
                    cursor=int(page1['pagination']['next_cursor']),
                    limit=10
                )
    """
    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    if name is not None:
        params["name"] = name
    if enabled is not None:
        params["enabled"] = enabled
    if template_backed is not None:
        params["template_backed"] = template_backed
    if cloned is not None:
        params["cloned"] = cloned
    if step_type is not None:
        params["step_type"] = step_type
    if stage is not None:
        params["stage"] = stage
    if execution is not None:
        params["execution"] = execution
    if tag is not None:
        params["tag"] = tag
    if include_attachments:
        params["include_attachments"] = include_attachments
    if attachment_target_type is not None:
        params["attachment_target_type"] = attachment_target_type
    if attachment_target_id is not None:
        params["attachment_target_id"] = attachment_target_id

    response = await client.http_client.get("/api/v1/controls", params=params)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def get_control(
    client: AgentControlClient,
    control_id: int,
) -> dict[str, Any]:
    """
    Get a control by ID.

    Args:
        client: AgentControlClient instance
        control_id: ID of the control

    Returns:
        Dictionary containing:
            - id: Control ID
            - name: Control name
            - data: Control definition or unrendered template control data

    Raises:
        httpx.HTTPError: If request fails
        HTTPException 404: Control not found

    Example:
        async with AgentControlClient() as client:
            control = await get_control(client, control_id=5)
            print(f"Control: {control['name']}")
            print(f"Enabled: {control['data']['enabled']}")
    """
    response = await client.http_client.get(f"/api/v1/controls/{control_id}")
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def list_control_versions(
    client: AgentControlClient,
    control_id: int,
    cursor: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    List version-history summaries for a control.

    Args:
        client: AgentControlClient instance
        control_id: ID of the control
        cursor: Version number to start after (newest-first pagination)
        limit: Maximum number of versions to return

    Returns:
        Dictionary containing:
            - versions: List of version summaries
            - pagination: Object with limit, total, next_cursor, has_more
    """
    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor

    response = await client.http_client.get(
        f"/api/v1/controls/{control_id}/versions",
        params=params,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def get_control_version(
    client: AgentControlClient,
    control_id: int,
    version_num: int,
) -> dict[str, Any]:
    """
    Get a specific version snapshot for a control.

    Args:
        client: AgentControlClient instance
        control_id: ID of the control
        version_num: Control version number to fetch

    Returns:
        Dictionary containing version metadata and the raw snapshot payload.
    """
    response = await client.http_client.get(
        f"/api/v1/controls/{control_id}/versions/{version_num}"
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def create_control(
    client: AgentControlClient,
    name: str,
    data: dict[str, Any] | ControlDefinition | TemplateControlInput,
) -> dict[str, Any]:
    """
    Create a new control with a unique name and configuration.

    Control names are canonicalized by the API (leading/trailing whitespace
    is trimmed); callers may pass trimmed names for consistency.

    Args:
        client: AgentControlClient instance
        name: Unique name for the control
        data: Raw control definition or template-backed control input

    Returns:
        Dictionary containing:
            - control_id: ID of the created control
            - configured: Always True because create requires data

    Raises:
        httpx.HTTPError: If request fails
        HTTPException 409: Control with this name already exists
        HTTPException 422: If data doesn't match schema
        HTTPException 500: Database error during creation

    Example:
        async with AgentControlClient() as client:
            result = await create_control(
                client,
                name="ssn-blocker",
                data={
                    "execution": "server",
                    "scope": {"step_types": ["llm"], "stages": ["post"]},
                    "condition": {
                        "selector": {"path": "output"},
                        "evaluator": {
                            "name": "regex",
                            "config": {"pattern": r"\\d{3}-\\d{2}-\\d{4}"}
                        }
                    },
                    "action": {"decision": "deny"}
                }
            )
            print(f"Created and configured control: {result['control_id']}")
    """
    payload: dict[str, Any] = {"name": name}
    if isinstance(data, (ControlDefinition, TemplateControlInput)):
        payload["data"] = data.model_dump(mode="json", exclude_none=True)
    else:
        payload["data"] = cast(dict[str, Any], data)

    response = await client.http_client.put(
        "/api/v1/controls",
        json=payload,
    )
    response.raise_for_status()
    result = cast(dict[str, Any], response.json())

    result["configured"] = True
    return result


async def clone_and_bind_control(
    client: AgentControlClient,
    control_id: int,
    *,
    target_type: str,
    target_id: str,
    name: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """
    Clone an existing control and bind the clone to a target in one API call.

    Args:
        client: AgentControlClient instance
        control_id: Source control ID to clone
        target_type: Opaque attachment kind
        target_id: Opaque external target identifier
        name: Optional unique name for the cloned control
        enabled: Whether the created binding is active

    Returns:
        Dictionary containing id, name, cloned_from_control_id, and binding_id.
    """
    payload: dict[str, Any] = {
        "target_binding": {
            "target_type": target_type,
            "target_id": target_id,
            "enabled": enabled,
        }
    }
    if name is not None:
        payload["name"] = name

    response = await client.http_client.post(
        f"/api/v1/controls/{control_id}/clone-and-bind",
        json=payload,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def set_control_data(
    client: AgentControlClient,
    control_id: int,
    data: dict[str, Any] | ControlDefinition | TemplateControlInput
) -> dict[str, Any]:
    """
    Set the configuration data for a control.

    This defines what the control actually does (condition tree, action, scope).

