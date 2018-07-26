from collections.abc import Sequence
from typing import Any

from agent_control_engine import list_evaluators
from agent_control_models.agent import Agent as APIAgent
from agent_control_models.agent import StepSchema
from agent_control_models.controls import ControlDefinition, ControlDefinitionRuntime
from agent_control_models.errors import ErrorCode, ValidationErrorItem
from agent_control_models.policy import Control as APIControl
from agent_control_models.server import (
    AgentControlsResponse,
    AgentSummary,
    AssocResponse,
    ConflictMode,
    DeletePolicyResponse,
    EvaluatorSchema,
    GetAgentPoliciesResponse,
    GetAgentResponse,
    GetPolicyResponse,
    InitAgentEvaluatorRemoval,
    InitAgentOverwriteChanges,
    InitAgentRequest,
    InitAgentResponse,
    ListAgentsResponse,
    PaginationInfo,
    PatchAgentRequest,
    PatchAgentResponse,
    RemoveAgentControlResponse,
    SetPolicyResponse,
    StepKey,
)
from fastapi import APIRouter, Depends, Query, Request
from jsonschema_rs import ValidationError as JSONSchemaValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_framework import Operation, Principal, get_authorizer, require_operation
from ..db import get_async_db
from ..errors import (
    APIValidationError,
    BadRequestError,
    ConflictError,
    DatabaseError,
    ForbiddenError,
    NotFoundError,
)
from ..logging_utils import get_logger
from ..models import (
    Agent,
    AgentData,
    Control,
    Policy,
    agent_policies,
)
from ..services.agent_names import normalize_agent_name_or_422
from ..services.controls import (
    AgentControlEnabledState,
    AgentControlRenderedState,
    ControlService,
)
from ..services.evaluator_utils import (
    parse_evaluator_ref_full,
    validate_config_against_schema,
)
from ..services.query_utils import escape_like_pattern
from ..services.schema_compat import (
    check_schema_compatibility,
    format_compatibility_error,
)

router = APIRouter(prefix="/agents", tags=["agents"])

_logger = get_logger(__name__)

# Cache for built-in evaluator names (populated on first use)
_BUILTIN_EVALUATOR_NAMES: set[str] | None = None

# Pagination constants
_DEFAULT_PAGINATION_OFFSET = 0
_DEFAULT_PAGINATION_LIMIT = 20
_MAX_PAGINATION_LIMIT = 100
_CORRUPTED_AGENT_DATA_MESSAGE = "Stored agent data is corrupted and cannot be parsed."

type StepKeyTuple = tuple[str, str]


def _complete_target_context(
    target_type: object | None,
    target_id: object | None,
) -> dict[str, str] | None:
    """Return target context only when both halves are present strings."""
    if not isinstance(target_type, str) or not isinstance(target_id, str):
        return None
    if not target_type or not target_id:
        return None
    return {"target_type": target_type, "target_id": target_id}


async def _init_agent_target_context(request: Request) -> dict[str, str] | None:
    """Extract optional target context from an ``initAgent`` body."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001  malformed JSON, defer to endpoint validation
        return None
    if not isinstance(body, dict):
        return None
    return _complete_target_context(body.get("target_type"), body.get("target_id"))


def _agent_controls_target_context(request: Request) -> dict[str, str] | None:
    """Extract optional target context from ``GET /agents/{name}/controls``."""
    return _complete_target_context(
        request.query_params.get("target_type"),
        request.query_params.get("target_id"),
    )


async def _authorize_target_read_if_present(
    request: Request,
    context: dict[str, str] | None,
) -> Principal | None:
    """Require target read authorization before returning target-merged controls.

    Agent endpoints that accept optional target context have two separate
    authorization decisions:

    - the endpoint operation itself (for example, ``agents.create``), whose
      result is exposed to the route as ``principal``;
    - the target binding read (``control_bindings.read``), whose result is
      exposed as ``target_principal``.

    Keeping the results separate lets the route verify that the caller's
    namespace and the target's resolved namespace agree before merging
    target-bound controls into the response.
    """
    if context is None:
        return None
    return await get_authorizer(Operation.CONTROL_BINDINGS_READ).authorize(
        request,
        Operation.CONTROL_BINDINGS_READ,
        context,
    )


async def _init_agent_target_principal(request: Request) -> Principal | None:
    return await _authorize_target_read_if_present(
        request,
        await _init_agent_target_context(request),
    )


async def _agent_controls_target_principal(request: Request) -> Principal | None:
    return await _authorize_target_read_if_present(
        request,
        _agent_controls_target_context(request),
    )


def _ensure_target_principal_matches_namespace(
    principal: Principal,
    target_principal: Principal | None,
) -> None:
    """Fail closed if the target authorization resolves to a different namespace."""
    if target_principal is None:
        return
    if target_principal.namespace_key == principal.namespace_key:
        return
    raise ForbiddenError(
        error_code=ErrorCode.AUTH_INSUFFICIENT_PRIVILEGES,
        detail="Target authorization resolved to a different namespace.",
        hint="Ensure the credential is scoped to the requested target and namespace.",
    )


async def _authorize_existing_agent_overwrite(
    request: Request,
    principal: Principal,
) -> None:
    update_principal = await get_authorizer(Operation.AGENTS_UPDATE).authorize(
        request,
        Operation.AGENTS_UPDATE,
    )
    if update_principal.namespace_key == principal.namespace_key:
        return
    raise ForbiddenError(
        error_code=ErrorCode.AUTH_INSUFFICIENT_PRIVILEGES,
        detail="Update authorization resolved to a different namespace.",
        hint="Ensure the credential is scoped to the requested agent namespace.",
    )


# =============================================================================
# List Agents Models
# =============================================================================


def _get_builtin_evaluator_names() -> set[str]:
    """Get built-in evaluator names (cached)."""
    global _BUILTIN_EVALUATOR_NAMES
    if _BUILTIN_EVALUATOR_NAMES is None:
        _BUILTIN_EVALUATOR_NAMES = set(list_evaluators().keys())
    return _BUILTIN_EVALUATOR_NAMES


def _validate_controls_for_agent(agent: Agent, controls: list[Control]) -> list[str]:
    """Validate controls can run on this agent."""
    errors: list[str] = []

    # Parse agent's registered evaluators
    try:
        agent_data = AgentData.model_validate(agent.data)
    except ValidationError:
        return [f"Agent '{agent.name}' has corrupted data"]

    agent_evaluators = {e.name: e for e in (agent_data.evaluators or [])}

    for control in controls:
        # Skip unrendered template controls - they have no evaluators to validate.
        if (
            isinstance(control.data, dict)
            and control.data.get("template") is not None
            and control.data.get("condition") is None
        ):
            continue

        try:
            control_definition = ControlDefinitionRuntime.model_validate(control.data)
        except ValidationError:
            errors.append(f"Control '{control.name}' has corrupted data")
            continue

        for _, evaluator_cfg in control_definition.iter_condition_leaf_parts():
            evaluator_name = evaluator_cfg.name
            parsed = parse_evaluator_ref_full(evaluator_name)
            if parsed.type != "agent":
                continue  # Built-in/external evaluator, already validated at control creation

            # Agent-scoped evaluator - check if target matches this agent
            if parsed.namespace != agent.name:
                errors.append(
                    f"Control '{control.name}' references evaluator '{evaluator_name}' "
                    f"which belongs to agent '{parsed.namespace}', not '{agent.name}'"
                )
                continue

            # Check if evaluator exists on this agent
            if parsed.local_name not in agent_evaluators:
                errors.append(
                    f"Control '{control.name}' references evaluator '{parsed.local_name}' "
                    f"which is not registered with agent '{agent.name}'. "
                    f"Register it via initAgent or use a different evaluator."
                )
                continue

            # Validate config against schema
            registered_ev = agent_evaluators[parsed.local_name]
            if registered_ev.config_schema:
                try:
                    validate_config_against_schema(
                        evaluator_cfg.config,
                        registered_ev.config_schema,
                    )
                except JSONSchemaValidationError as e:
                    errors.append(
                        f"Control '{control.name}' invalid config for "
                        f"'{parsed.local_name}': {e.message}"
                    )

    return errors


def _find_referencing_controls_for_removed_evaluators(
    controls: Sequence[APIControl],
    agent_name: str,
    remove_evaluator_set: set[str],
) -> list[tuple[str, str]]:
    """Return sorted unique control/evaluator pairs blocking evaluator removal."""
    referencing_control_set: set[tuple[str, str]] = set()

    for ctrl in controls:
        if not isinstance(ctrl.control, ControlDefinition):
            continue  # Skip unrendered template controls
        for _, evaluator_spec in ctrl.control.iter_condition_leaf_parts():
            evaluator_ref = evaluator_spec.name
            if ":" not in evaluator_ref:
                continue
            ref_agent, ref_eval = evaluator_ref.split(":", 1)
            if ref_agent == agent_name and ref_eval in remove_evaluator_set:
                referencing_control_set.add((ctrl.name, ref_eval))

    return sorted(referencing_control_set, key=lambda item: (item[0], item[1]))


async def _validate_policy_controls_for_agent(
    agent: Agent, policy_id: int, db: AsyncSession, *, namespace_key: str
) -> list[str]:
    """Validate all controls in a policy can run on this agent."""
    controls = await ControlService(db).list_controls_for_policy(
        policy_id, namespace_key=namespace_key
    )
    return _validate_controls_for_agent(agent, controls)


def _step_registration_changed(existing_step: StepSchema, incoming_step: StepSchema) -> bool:
    """Return True when non-key step registration fields differ."""
    return (
        existing_step.description != incoming_step.description
        or existing_step.input_schema != incoming_step.input_schema
        or existing_step.output_schema != incoming_step.output_schema
        or existing_step.metadata != incoming_step.metadata
    )


def _step_key_model(step_key: StepKeyTuple) -> StepKey:
    """Convert an internal step tuple key to API model."""
    step_type, step_name = step_key
    return StepKey(type=step_type, name=step_name)


async def _build_overwrite_evaluator_removals(
    agent: Agent,
    removed_evaluators: set[str],
    db: AsyncSession,
    *,
    namespace_key: str,
) -> list[InitAgentEvaluatorRemoval]:
    """Build evaluator removal details, including active-control references."""
    if not removed_evaluators:
        return []

    try:
        controls = await ControlService(db).list_controls_for_agent(
            agent.name,
            namespace_key=namespace_key,
            allow_invalid_step_name_regex=True,
        )
    except APIValidationError:
        _logger.warning(
            "Skipping evaluator removal reference checks for agent '%s' "
            "due to invalid control data",
            agent.name,
            exc_info=True,
        )
        return [InitAgentEvaluatorRemoval(name=name) for name in sorted(removed_evaluators)]

    references_by_evaluator: dict[str, set[tuple[int, str]]] = {}
    for control in controls:
        if not isinstance(control.control, ControlDefinition):
            continue  # Skip unrendered template controls
        for _, evaluator_spec in control.control.iter_condition_leaf_parts():
            evaluator_ref = evaluator_spec.name
            parsed = parse_evaluator_ref_full(evaluator_ref)
            if parsed.type != "agent":
                continue
            if parsed.namespace != agent.name:
                continue
            if parsed.local_name not in removed_evaluators:
                continue
            references_by_evaluator.setdefault(parsed.local_name, set()).add(
                (control.id, control.name)
            )

    removals: list[InitAgentEvaluatorRemoval] = []
    for evaluator_name in sorted(removed_evaluators):
        references = references_by_evaluator.get(evaluator_name)
        if references is None:
            removals.append(InitAgentEvaluatorRemoval(name=evaluator_name))
            continue
        sorted_references = sorted(references, key=lambda item: (item[1], item[0]))
        removals.append(
            InitAgentEvaluatorRemoval(
                name=evaluator_name,
                referenced_by_active_controls=True,
                control_ids=[control_id for control_id, _ in sorted_references],
                control_names=[control_name for _, control_name in sorted_references],
            )
        )
    return removals


@router.get(
    "",
    response_model=ListAgentsResponse,
    summary="List all agents",
    response_description="Paginated list of agent summaries",
)
async def list_agents(
    cursor: str | None = None,
    limit: int = _DEFAULT_PAGINATION_LIMIT,
    name: str | None = None,
    db: AsyncSession = Depends(get_async_db),
    principal: Principal = Depends(require_operation(Operation.AGENTS_READ)),
) -> ListAgentsResponse:
    """
    List all registered agents with cursor-based pagination.

    Returns a summary of each agent including identifier, policy associations,
    and counts of registered steps and evaluators. Results are scoped to
    the request's namespace; agents in other namespaces are not visible.

    Args:
        cursor: Optional cursor for pagination (last agent name from previous page)
        limit: Pagination limit (default 20, max 100)
        name: Optional name filter (case-insensitive partial match)
        db: Database session (injected)
        principal: Authorized request principal

    Returns:
        ListAgentsResponse with agent summaries and pagination info
    """
    namespace_key = principal.namespace_key

    # Clamp limit
    limit = min(max(1, limit), _MAX_PAGINATION_LIMIT)

    # Build base filter for name search
    name_filter = Agent.name.ilike(f"%{escape_like_pattern(name)}%", escape="\\") if name else None

    # Get total count (with name filter if provided)
    count_query = (
        select(func.count()).select_from(Agent).where(Agent.namespace_key == namespace_key)
    )
    if name_filter is not None:
        count_query = count_query.where(name_filter)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Build query with cursor-based pagination
    # Order by created_at DESC, then by name DESC for stable ordering
    query = (
        select(Agent)
        .where(Agent.namespace_key == namespace_key)
        .order_by(Agent.created_at.desc(), Agent.name.desc())
    )

    # Apply name filter if provided
    if name_filter is not None:
        query = query.where(name_filter)

    # If cursor provided, filter to get items after the cursor.
    # The cursor lookup is namespace-scoped so a duplicate name in
    # another namespace cannot redirect pagination.
    if cursor:
        cursor_name = normalize_agent_name_or_422(cursor, field_name="cursor")
        cursor_agent_result = await db.execute(
            select(Agent).where(
                Agent.name == cursor_name,
                Agent.namespace_key == namespace_key,
            )
        )
        cursor_agent = cursor_agent_result.scalars().first()
        if cursor_agent:
            query = query.where(
                (Agent.created_at < cursor_agent.created_at)
                | ((Agent.created_at == cursor_agent.created_at) & (Agent.name < cursor_agent.name))
            )

    # Fetch limit + 1 to check if there are more pages
    query = query.limit(limit + 1)
    result = await db.execute(query)
    agents: Sequence[Agent] = result.scalars().all()

    # Check if there are more pages
    has_more = len(agents) > limit
    if has_more:
        agents = agents[:-1]  # Remove the extra item

    # Determine next cursor (name of last agent in this page)
    next_cursor: str | None = None
    if has_more and agents:
        next_cursor = agents[-1].name

    control_counts_map: dict[str, int] = {}
    policy_ids_map: dict[str, list[int]] = {}
    control_service = ControlService(db)

    if agents:
        agent_names = [agent.name for agent in agents]

        policy_ids_query = (
            select(
                agent_policies.c.agent_name,
                agent_policies.c.policy_id,
            )
            .where(
                agent_policies.c.namespace_key == namespace_key,
                agent_policies.c.agent_name.in_(agent_names),
            )
            .order_by(agent_policies.c.agent_name, agent_policies.c.policy_id)
        )
        policy_ids_result = await db.execute(policy_ids_query)
        for assoc_agent_name, policy_id in policy_ids_result.all():
            policy_ids_map.setdefault(assoc_agent_name, []).append(policy_id)

        control_counts_map = await control_service.list_active_control_counts_by_agent(
            agent_names,
            namespace_key=namespace_key,
        )

    # Build summaries
    summaries: list[AgentSummary] = []
    for agent in agents:
        step_count = 0
        evaluator_count = 0

        # Parse agent data to get counts
        try:
            data_model = AgentData.model_validate(agent.data)
            step_count = len(data_model.steps or [])
            evaluator_count = len(data_model.evaluators or [])
        except ValidationError:
            # If data is corrupted, log and use zero counts
            _logger.warning("Agent '%s' has invalid data, using zero counts", agent.name)

        # Get active controls count from batched query result
        active_controls = control_counts_map.get(agent.name, 0)

        policy_ids = policy_ids_map.get(agent.name, [])

        summaries.append(
            AgentSummary(
                agent_name=agent.name,
                policy_ids=policy_ids,
                created_at=agent.created_at.isoformat() if agent.created_at else None,
                step_count=step_count,
                evaluator_count=evaluator_count,
                active_controls_count=active_controls,
            )
        )

    return ListAgentsResponse(
        agents=summaries,
        pagination=PaginationInfo(
            limit=limit,
            total=total,
            next_cursor=next_cursor,
            has_more=has_more,
        ),
    )


@router.post(
    "/initAgent",
    response_model=InitAgentResponse,
    summary="Initialize or update an agent",
    response_description="Agent registration status with active controls",
)
async def init_agent(
    request: InitAgentRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
    principal: Principal = Depends(require_operation(Operation.AGENTS_CREATE)),
    target_principal: Principal | None = Depends(_init_agent_target_principal),
) -> InitAgentResponse:
    """
    Register a new agent or update an existing agent's steps and metadata.

    This endpoint is idempotent:
    - If the agent name doesn't exist, creates a new agent
    - If the agent name exists, updates registration data in place

    conflict_mode controls registration conflict handling:
    - strict (default): preserve compatibility checks and conflict errors
    - overwrite: latest init payload replaces steps/evaluators and returns change summary

    The returned ``controls`` list is the de-duplicated union of the agent's
    direct controls, policy-derived controls, and (when ``target_type`` and
    ``target_id`` are both supplied on the request) controls attached to that
    target via enabled bindings in the same namespace. The same merge applies
    on ``GET /agents/{name}/controls`` and ``POST /evaluation``. Bindings can
    pre-exist the agent row, so a newly created agent that registers with
    target context can observe target controls immediately.

    Args:
        request: Agent metadata and step schemas
        db: Database session (injected)
        principal: Authorized request principal for the agent create operation
        target_principal: Optional principal from the target binding read check

    Returns:
        InitAgentResponse with created flag and the effective controls
    """
    namespace_key = principal.namespace_key
    _ensure_target_principal_matches_namespace(principal, target_principal)

    # Check for evaluator name collisions with built-in evaluators
    builtin_names = _get_builtin_evaluator_names()
    for ev in request.evaluators:
        if ev.name in builtin_names:
            raise ConflictError(
                error_code=ErrorCode.EVALUATOR_NAME_CONFLICT,
                detail=f"Evaluator name '{ev.name}' conflicts with built-in evaluator.",
                resource="Evaluator",
                resource_id=ev.name,
                hint="Choose a different name that does not conflict with built-in evaluators.",
                errors=[
                    ValidationErrorItem(
                        resource="Evaluator",
                        field="name",
                        code="name_conflict",
                        message=f"Name '{ev.name}' conflicts with a built-in evaluator",
                        value=ev.name,
                    )
                ],
            )

    # Build incoming_steps_by_key and validate no duplicates in single pass
    incoming_steps_by_key: dict[StepKeyTuple, StepSchema] = {}
    for step in request.steps:
        step_key: StepKeyTuple = (step.type, step.name)
        if step_key in incoming_steps_by_key:
            raise BadRequestError(
                error_code=ErrorCode.VALIDATION_ERROR,
                detail=f"Duplicate step name detected: type='{step.type}', name='{step.name}'. "
                f"Each step must have a unique (type, name) combination within an agent.",
                errors=[
                    ValidationErrorItem(
                        resource="Step",
                        field="name",
                        code="duplicate_step_name",
                        message=(
                            f"Step (type='{step.type}', name='{step.name}') "
                            f"appears multiple times in request"
                        ),
                    )
                ],
            )
        incoming_steps_by_key[step_key] = step

    result = await db.execute(
        select(Agent).where(
            Agent.name == request.agent.agent_name,
            Agent.namespace_key == namespace_key,
        )
    )
    existing: Agent | None = result.scalars().first()

    created = False

    if existing is None:
        created = True

        data_model = AgentData(
            agent_metadata=request.agent.model_dump(mode="json"),
            steps=list(request.steps),
            evaluators=list(request.evaluators),
        )

        new_agent = Agent(
            name=request.agent.agent_name,
            namespace_key=namespace_key,
            data=data_model.model_dump(mode="json"),
        )
        db.add(new_agent)
        try:
            await db.commit()
            _logger.info(
                f"Created agent '{request.agent.agent_name}' with {len(request.steps)} steps, "
                f"{len(request.evaluators)} evaluators"
            )
        except Exception:
            await db.rollback()
            _logger.error(
                f"Failed to create agent '{request.agent.agent_name}' ({request.agent.agent_name})",
                exc_info=True,
            )
            raise DatabaseError(
                detail=f"Failed to create agent '{request.agent.agent_name}': database error",
                resource="Agent",
                operation="create",
            )

        # Fall through to the terminal resolution so a newly created agent
        # registering with target context picks up pre-existing bindings.
        controls = await ControlService(db).list_controls_for_agent(
            new_agent.name,
            namespace_key=namespace_key,
            target_type=request.target_type,
            target_id=request.target_id,
        )
        return InitAgentResponse(created=created, controls=controls)

    if request.force_replace or request.conflict_mode == ConflictMode.OVERWRITE:
        await _authorize_existing_agent_overwrite(http_request, principal)

    # Parse existing data via AgentData Pydantic model
    try:
        data_model = AgentData.model_validate(existing.data)
    except ValidationError:
        if not request.force_replace:
            _logger.error(
                f"Failed to parse existing agent data for '{request.agent.agent_name}'",
                exc_info=True,
            )
            raise APIValidationError(
                error_code=ErrorCode.CORRUPTED_DATA,
                detail=(
                    f"Agent '{request.agent.agent_name}' has corrupted data and cannot be updated"
                ),
                resource="Agent",
                hint="Set force_replace=true in the request to replace the corrupted data.",
                errors=[
                    ValidationErrorItem(
                        resource="Agent",
                        field="data",
                        code="corrupted_data",
                        message=_CORRUPTED_AGENT_DATA_MESSAGE,
                    )
                ],
            )
        # User explicitly requested replacement
        _logger.warning(
            f"Force-replacing corrupted data for agent '{request.agent.agent_name}' "
            "due to force_replace=true.",
            exc_info=True,
        )
        data_model = AgentData(agent_metadata={}, steps=[], evaluators=[])

    steps_changed = False
    evaluators_changed = False
    force_write = request.force_replace  # Always persist when force_replace=true
    overwrite_applied = False
    overwrite_changes = InitAgentOverwriteChanges()

    # --- Update agent metadata ---
    new_metadata = request.agent.model_dump(mode="json")
    metadata_changed = data_model.agent_metadata != new_metadata
    if metadata_changed:
        data_model.agent_metadata = new_metadata

    new_steps: list[StepSchema]
    new_evaluators: list[EvaluatorSchema]

    if request.conflict_mode == ConflictMode.OVERWRITE:
        # Latest-init-wins: overwrite steps/evaluators exactly with incoming payload.
        existing_steps = list(data_model.steps or [])
        existing_steps_by_key = {(step.type, step.name): step for step in existing_steps}
        existing_step_keys = set(existing_steps_by_key)
        incoming_step_keys = set(incoming_steps_by_key)

        steps_added_keys = sorted(incoming_step_keys - existing_step_keys)
        steps_removed_keys = sorted(existing_step_keys - incoming_step_keys)
        steps_updated_keys = sorted(
            key
            for key in (existing_step_keys & incoming_step_keys)
            if _step_registration_changed(existing_steps_by_key[key], incoming_steps_by_key[key])
        )

        existing_evaluators = list(data_model.evaluators or [])
        existing_evals_by_name: dict[str, EvaluatorSchema] = {
            evaluator.name: evaluator for evaluator in existing_evaluators
        }
        incoming_evals_by_name: dict[str, EvaluatorSchema] = {
            evaluator.name: evaluator for evaluator in request.evaluators
        }
        existing_eval_names = set(existing_evals_by_name)
        incoming_eval_names = set(incoming_evals_by_name)

        evaluators_added_names = sorted(incoming_eval_names - existing_eval_names)
        evaluators_removed_names = sorted(existing_eval_names - incoming_eval_names)
        evaluators_updated_names = sorted(
            name
            for name in (existing_eval_names & incoming_eval_names)
            if (
                existing_evals_by_name[name].config_schema
                != incoming_evals_by_name[name].config_schema
                or existing_evals_by_name[name].description
                != incoming_evals_by_name[name].description
            )
        )

        evaluator_removals: list[InitAgentEvaluatorRemoval] = []
        if evaluators_removed_names:
            evaluator_removals = await _build_overwrite_evaluator_removals(
                existing,
                set(evaluators_removed_names),
                db,
                namespace_key=namespace_key,
            )

        overwrite_changes = InitAgentOverwriteChanges(
            metadata_changed=metadata_changed,
            steps_added=[_step_key_model(step_key) for step_key in steps_added_keys],
            steps_updated=[_step_key_model(step_key) for step_key in steps_updated_keys],
            steps_removed=[_step_key_model(step_key) for step_key in steps_removed_keys],
            evaluators_added=evaluators_added_names,
            evaluators_updated=evaluators_updated_names,
            evaluators_removed=evaluators_removed_names,
            evaluator_removals=evaluator_removals,
        )

        steps_changed = bool(steps_added_keys or steps_updated_keys or steps_removed_keys)
        evaluators_changed = bool(
            evaluators_added_names or evaluators_updated_names or evaluators_removed_names
        )
        overwrite_applied = bool(metadata_changed or steps_changed or evaluators_changed)

        new_steps = list(request.steps)
        new_evaluators = list(request.evaluators)
        data_model.steps = new_steps
        data_model.evaluators = new_evaluators
    else:
        # --- Process steps ---
        # Note: incoming_steps_by_key already built during validation above
        new_steps = []
        seen_steps: set[StepKeyTuple] = set()

        for step in data_model.steps or []:
            key: StepKeyTuple = (step.type, step.name)
            if key in incoming_steps_by_key:
                if key not in seen_steps:
                    incoming_step = incoming_steps_by_key[key]

                    # Compare only schema fields (type/name already matched by key)
                    # Avoid model_dump() allocations by direct field comparison
                    if (
                        step.input_schema != incoming_step.input_schema
                        or step.output_schema != incoming_step.output_schema
                    ):
                        raise ConflictError(
                            error_code=ErrorCode.SCHEMA_INCOMPATIBLE,
                            detail=(
                                "Step schema conflict for "
                                f"(type='{step.type}', name='{step.name}'). "
                                f"A step with this name already exists with a different schema."
                            ),
                            resource="Step",
                            resource_id=step.name,
                            hint=(
                                "Please use a different step name or ensure schemas match exactly."
                            ),
                            errors=[
                                ValidationErrorItem(
                                    resource="Step",
                                    field="schema",
                                    code="schema_mismatch",
                                    message=(
                                        f"Existing schema differs from incoming schema "
                                        f"for step '{step.name}'"
                                    ),
                                )
                            ],
                        )

                    new_steps.append(incoming_step)
                    seen_steps.add(key)
            else:
                new_steps.append(step)

        for key, step in incoming_steps_by_key.items():
            if key not in seen_steps:
                new_steps.append(step)
                steps_changed = True

        data_model.steps = new_steps

        # --- Process evaluators with schema compatibility check ---
        incoming_evals_by_name = {evaluator.name: evaluator for evaluator in request.evaluators}
        existing_evals_by_name = {
            evaluator.name: evaluator for evaluator in (data_model.evaluators or [])
        }
        new_evaluators = []

        # Check existing evaluators for compatibility
        for name, existing_ev in existing_evals_by_name.items():
            if name in incoming_evals_by_name:
                incoming_ev = incoming_evals_by_name[name]
                old_schema = existing_ev.config_schema
                new_schema = incoming_ev.config_schema

                # Short-circuit: only check compatibility if schemas differ
                if old_schema != new_schema:
                    is_compatible, compat_errors = check_schema_compatibility(
                        old_schema, new_schema
                    )
                    if not is_compatible:
                        raise ConflictError(
                            error_code=ErrorCode.SCHEMA_INCOMPATIBLE,
                            detail=format_compatibility_error(name, compat_errors),
                            resource="Evaluator",
                            resource_id=name,
                            hint="Ensure backward compatibility or use a new evaluator name.",
                            errors=[
                                ValidationErrorItem(
                                    resource="Evaluator",
                                    field="config_schema",
                                    code="schema_incompatible",
                                    message=err,
                                )
                                for err in compat_errors
                            ],
                        )

                # Check if evaluator changed (compare fields directly, avoid model_dump())
                if (
                    existing_ev.config_schema != incoming_ev.config_schema
                    or existing_ev.description != incoming_ev.description
                ):
                    evaluators_changed = True
                new_evaluators.append(incoming_ev)
            else:
                # Keep existing evaluator not in incoming request
                new_evaluators.append(existing_ev)

        # Add new evaluators
        for name, evaluator in incoming_evals_by_name.items():
            if name not in existing_evals_by_name:
                new_evaluators.append(evaluator)
                evaluators_changed = True

        data_model.evaluators = new_evaluators

    if (
        not request.force_replace
        and request.conflict_mode != ConflictMode.OVERWRITE
        and (steps_changed or evaluators_changed or metadata_changed)
    ):
        await _authorize_existing_agent_overwrite(http_request, principal)

    if steps_changed or evaluators_changed or metadata_changed or force_write:
        existing.data = data_model.model_dump(mode="json")

        try:
            await db.commit()
            _logger.info(
                f"Updated agent '{request.agent.agent_name}' with {len(new_steps)} steps, "
                f"{len(new_evaluators)} evaluators"
            )
        except Exception:
            await db.rollback()
            _logger.error(
                f"Failed to update agent '{request.agent.agent_name}' ({request.agent.agent_name})",
                exc_info=True,
            )
            raise DatabaseError(
                detail=f"Failed to update agent '{request.agent.agent_name}': database error",
                resource="Agent",
                operation="update",
            )

    controls = await ControlService(db).list_controls_for_agent(
        existing.name,
        namespace_key=namespace_key,
        target_type=request.target_type,
        target_id=request.target_id,
    )

    return InitAgentResponse(
        created=created,
        controls=controls,
        overwrite_applied=overwrite_applied,
        overwrite_changes=overwrite_changes,
    )


@router.get(
    "/{agent_name}",
    response_model=GetAgentResponse,
    summary="Get agent details",
    response_description="Agent metadata and registered steps",
)
async def get_agent(
    agent_name: str,
    db: AsyncSession = Depends(get_async_db),
    principal: Principal = Depends(require_operation(Operation.AGENTS_READ)),
) -> GetAgentResponse:
    """
    Retrieve agent metadata and all registered steps.

    Returns the latest version of each step (deduplicated by type+name).

    Args:
        agent_name: Agent identifier
        db: Database session (injected)
        principal: Authorized request principal

    Returns:
        GetAgentResponse with agent metadata and step list

    Raises:
        HTTPException 404: Agent not found
        HTTPException 422: Agent data is corrupted
    """
    namespace_key = principal.namespace_key
    agent_name = normalize_agent_name_or_422(agent_name)
    result = await db.execute(
        select(Agent).where(Agent.name == agent_name, Agent.namespace_key == namespace_key)
    )
    existing: Agent | None = result.scalars().first()
    if existing is None:
        raise NotFoundError(
            error_code=ErrorCode.AGENT_NOT_FOUND,
            detail=f"Agent with name '{agent_name}' not found",
            resource="Agent",
            resource_id=str(agent_name),
            hint=(
                "Verify the agent name is correct and the agent has been registered via initAgent."
            ),
        )

    try:
