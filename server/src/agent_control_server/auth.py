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
