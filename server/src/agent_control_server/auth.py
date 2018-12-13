"""
API key authentication for Agent Control Server.

This module provides flexible authentication dependencies that can be applied
to individual routers or endpoints with different security requirements.

Two credential sources are supported (checked in this order):

1. **X-API-Key header** — used by SDKs and programmatic clients.
2. **Session JWT cookie** — used by the browser UI after ``POST /api/login``.

If the header is present it is used exclusively (succeed or fail).  The cookie
is only checked when no header is provided.

Usage:
    # In a router file:
    from ..auth import require_api_key, require_admin_key

    # Apply to entire router (in main.py)
    app.include_router(router, dependencies=[Depends(require_api_key)])

    # Or apply to specific endpoints
    @router.get("/sensitive", dependencies=[Depends(require_admin_key)])
    async def sensitive_endpoint():
        ...

    # Access the validated key info in endpoint
    @router.get("/whoami")
    async def whoami(client: AuthenticatedClient = Depends(require_api_key)):
        return {"key_prefix": client.key_id}
"""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from agent_control_models.errors import ErrorCode, ErrorReason
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from .config import auth_settings
from .errors import APIError, AuthenticationError, ForbiddenError
from .logging_utils import get_logger

_logger = get_logger(__name__)


class AuthLevel(Enum):
    """Authentication level for categorizing access."""

    NONE = "none"  # No authentication required (auth disabled)
    API_KEY = "api_key"  # Standard API key required
    ADMIN = "admin"  # Admin API key required


@dataclass
class AuthenticatedClient:
    """
    Represents an authenticated API client.

    This dataclass provides information about the authenticated request,
    useful for logging, auditing, or conditional logic.
    """

    api_key: str
    is_admin: bool
    auth_level: AuthLevel

    @property
    def key_id(self) -> str:
        """Return a safe identifier for the key (first 8 chars + ellipsis)."""
        if len(self.api_key) > 8:
            return self.api_key[:8] + "..."
        return "***"


# Header extractor - doesn't validate, just extracts
_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,  # Don't auto-raise; we handle errors ourselves
    description="API key for authentication. Required for all protected endpoints.",
)


async def get_api_key_from_header(
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """
    Extract API key from header without validation.

    Use this when you need the raw key value for custom validation logic.
    """
    return api_key


def _authenticate_via_cookie(request: Request) -> AuthenticatedClient | None:
    """Try to authenticate using the session JWT cookie.

    Returns an ``AuthenticatedClient`` on success or ``None`` when no valid
    cookie is present.  Importing here avoids a circular import with
    ``endpoints.system`` (both share ``config`` but this module must not
    import endpoint code at module level).
    """
    from .endpoints.system import SESSION_COOKIE_NAME, decode_session_jwt

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    claims = decode_session_jwt(token)
    if claims is None:
        _logger.debug("Session cookie present but JWT is invalid or expired")
        return None

    is_admin: bool = claims.get("is_admin", False)
    auth_level = AuthLevel.ADMIN if is_admin else AuthLevel.API_KEY
    _logger.debug("Authenticated request via session cookie (%s)", auth_level.value)
    return AuthenticatedClient(
        api_key="",
        is_admin=is_admin,
        auth_level=auth_level,
    )


async def _validate_api_key(
    api_key: str | None,
    request: Request,
    require_admin: bool = False,
) -> AuthenticatedClient:
    """
    Internal validation logic for API keys.

    Credential precedence:
    1. ``X-API-Key`` header (if present, used exclusively — succeed or fail).
    2. Session JWT cookie (checked only when no header is provided).

    Args:
        api_key: The API key from the request header (may be None)
        request: The incoming request (used to read cookies)
        require_admin: Whether admin privileges are required

    Returns:
        AuthenticatedClient with key details

    Raises:
        AuthenticationError: If authentication fails
        ForbiddenError: If insufficient privileges
