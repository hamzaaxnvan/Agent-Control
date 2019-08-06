"""HTTP endpoints for managing the ``control_bindings`` table."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_control_models.errors import ErrorCode
from agent_control_models.server import (
    CreateControlBindingRequest,
    CreateControlBindingResponse,
    DeleteControlBindingByKeyRequest,
    DeleteControlBindingByKeyResponse,
    DeleteControlBindingResponse,
    GetControlBindingResponse,
    ListControlBindingsResponse,
    PaginationInfo,
    PatchControlBindingByKeyRequest,
    PatchControlBindingRequest,
    PatchControlBindingResponse,
    UpsertControlBindingRequest,
    UpsertControlBindingResponse,
)
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_framework import Operation, Principal, get_authorizer, require_operation
from ..auth_framework.core import IdentityResolver
from ..db import AsyncSessionLocal, get_async_db
from ..errors import BadRequestError, ForbiddenError, NotFoundError
from ..models import ControlBinding
from ..services.control_bindings import ControlBindingsService

router = APIRouter(prefix="/control-bindings", tags=["control-bindings"])

_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100


async def _binding_body_context(request: Request) -> dict[str, Any]:
    """Surface ``(target_type, target_id)`` to the authorization context.

    The body-bearing binding endpoints carry the target identifiers in
    the request payload. Authorization providers can use those
    identifiers when a request needs target-scoped access checks.

    FastAPI caches the parsed body, so the endpoint's own Pydantic
    request model still binds normally.
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001  malformed JSON falls through to endpoint validation
        return {}
    if not isinstance(body, dict):
        return {}
    return {
        "target_type": body.get("target_type"),
        "target_id": body.get("target_id"),
    }


async def _binding_list_context(request: Request) -> dict[str, Any]:
    """Surface optional target query parameters to authorization context.

    When the GET list endpoint is called with ``target_type`` and
    ``target_id`` query params, the request is target-scoped and the
    request context includes those identifiers. When neither is present
    the request is namespace-wide and forwards no target context.
    """
    target_type = request.query_params.get("target_type")
    target_id = request.query_params.get("target_id")
    if target_type is None and target_id is None:
        return {}
    return {"target_type": target_type, "target_id": target_id}


def _require_binding_operation(
    operation: Operation,
) -> Callable[..., Awaitable[Principal]]:
    """Use stored-target authorization when the provider opts in."""

    async def dependency(request: Request, binding_id: int) -> Principal:
        authorizer = get_authorizer(operation)
        if (
            not isinstance(authorizer, IdentityResolver)
            or not authorizer.binding_target_authorization
        ):
            # Preserve the existing single namespace-wide authorization call
            # for providers without an independent identity lookup. Their
            # operation contract may reject a new target context altogether.
            return await authorizer.authorize(request, operation)

        identity = await authorizer.resolve_identity(request, operation)
        # Use a short-lived session so no database connection is held while the
        # authorization provider performs a potentially remote request.
        async with AsyncSessionLocal() as db:
            target_type, target_id = await ControlBindingsService(
                db
            ).get_binding_target_for_authorization_or_404(
                namespace_key=identity.namespace_key, binding_id=binding_id
            )
