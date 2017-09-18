from agent_control_models.errors import ErrorCode
from agent_control_models.server import (
    AssocResponse,
    CreatePolicyRequest,
    CreatePolicyResponse,
    GetPolicyControlsResponse,
)
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_framework import Operation, Principal, require_operation
from ..db import get_async_db
from ..errors import ConflictError, DatabaseError, NotFoundError
from ..logging_utils import get_logger
from ..models import Policy
from ..services.controls import ControlService

router = APIRouter(prefix="/policies", tags=["policies"])

_logger = get_logger(__name__)


@router.put(
    "",
    response_model=CreatePolicyResponse,
    summary="Create a new policy",
    response_description="Created policy ID",
)
async def create_policy(
    request: CreatePolicyRequest,
    db: AsyncSession = Depends(get_async_db),
    principal: Principal = Depends(require_operation(Operation.POLICIES_CREATE)),
) -> CreatePolicyResponse:
    """
    Create a new empty policy with a unique name.

    Policies contain controls and can be assigned to agents.
    A newly created policy has no controls until they are explicitly added.

    Args:
        request: Policy creation request with unique name
        db: Database session (injected)

    Returns:
        CreatePolicyResponse with the new policy's ID

    Raises:
        HTTPException 409: Policy with this name already exists
        HTTPException 500: Database error during creation
    """
    namespace_key = principal.namespace_key
    # Uniqueness check
    existing = await db.execute(
        select(Policy.id).where(
            Policy.namespace_key == namespace_key,
            Policy.name == request.name,
        )
    )
    if existing.first() is not None:
        raise ConflictError(
            error_code=ErrorCode.POLICY_NAME_CONFLICT,
            detail=f"Policy with name '{request.name}' already exists",
            resource="Policy",
            resource_id=request.name,
            hint="Choose a different name or update the existing policy.",
        )

    policy = Policy(namespace_key=namespace_key, name=request.name)
    db.add(policy)
    try:
        await db.commit()
        await db.refresh(policy)
    except Exception:
        await db.rollback()
        _logger.error(
            f"Failed to create policy '{request.name}'",
            exc_info=True,
        )
        raise DatabaseError(
            detail=f"Failed to create policy '{request.name}': database error",
            resource="Policy",
            operation="create",
        )
    return CreatePolicyResponse(policy_id=policy.id)


@router.post(
    "/{policy_id}/controls/{control_id}",
    response_model=AssocResponse,
    summary="Add control to policy",
    response_description="Success confirmation",
)
async def add_control_to_policy(
    policy_id: int,
    control_id: int,
    db: AsyncSession = Depends(get_async_db),
    principal: Principal = Depends(require_operation(Operation.POLICIES_UPDATE)),
