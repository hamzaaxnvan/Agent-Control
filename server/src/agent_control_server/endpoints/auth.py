"""Auth endpoints (runtime token exchange).

The runtime auth flow is two-phase: this endpoint is phase one. The
caller presents a long-lived credential plus ``(target_type,
target_id)``; the configured authorization provider authenticates the
credential and authorizes the implied
``runtime.token_exchange`` operation. On success, this endpoint
mints a short-lived local runtime token bound to the supplied target
and returns it. Subsequent target-bearing runtime calls present the
returned token, which is verified locally by
the runtime JWT provider.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from agent_control_models.errors import ErrorCode, ErrorReason, ValidationErrorItem
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth_framework import Operation, Principal, require_operation
from ..auth_framework.config import runtime_auth_config
from ..auth_framework.runtime_token import (
    RuntimeTokenError,
    UpstreamGrantExpiredError,
    mint_runtime_token,
)
from ..errors import APIError, APIValidationError, BadRequestError
from ..logging_utils import get_logger

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = get_logger(__name__)


def _log_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class RuntimeTokenExchangeRequest(BaseModel):
    """Body for the runtime token exchange endpoint."""

    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(
        ..., description="Opaque target kind (e.g., ``session``).", min_length=1
    )
    target_id: str = Field(..., description="Opaque target identifier.", min_length=1)


class RuntimeTokenExchangeResponse(BaseModel):
    """Issued runtime token plus its expiry."""

    token: str = Field(..., description="Short-lived runtime token (HS256 JWT).")
    expires_at: datetime = Field(..., description="UTC timestamp at which the token expires.")
    target_type: str = Field(..., description="Target the token is bound to.")
    target_id: str = Field(..., description="Target the token is bound to.")
    scopes: list[str] = Field(
        ..., description="Granted runtime scopes; always includes ``runtime.use``."
    )


def _exchange_body_validation_error() -> APIValidationError:
    return APIValidationError(
        error_code=ErrorCode.VALIDATION_ERROR,
        detail="Runtime token exchange body must be a valid JSON object.",
        hint="Provide a JSON object containing target_type and target_id.",
    )


def _validate_exchange_target_field(
    body: dict[str, Any], field: str
) -> ValidationErrorItem | None:
    if field not in body:
        return ValidationErrorItem(
            resource="Request",
            field=field,
            code="missing",
            message="Field required",
        )

    value = body[field]
    if not isinstance(value, str):
        return ValidationErrorItem(
