"""System-level endpoints: UI configuration discovery, login, and logout.

These endpoints let the static UI bundle:
 - Discover whether API-key authentication is enabled.
 - Exchange an API key for a signed JWT stored in an HttpOnly cookie.
 - Clear the session cookie on logout.

The JWT cookie is accepted as an alternative credential by the ``require_api_key``
dependency so that browser clients never need to store or transmit raw keys after
the initial login POST.
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Final

import jwt
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from ..auth import AuthLevel, OptionalAPIKey
from ..config import auth_settings, settings
from ..logging_utils import get_logger

router = APIRouter(prefix="", tags=["system"])

_logger = get_logger(__name__)

SESSION_COOKIE_NAME: Final[str] = "agent_control_session"
JWT_ALGORITHM: Final[str] = "HS256"
SESSION_MAX_AGE_SECONDS: Final[int] = 30 * 24 * 60 * 60  # 1 month


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class AuthMode(StrEnum):
    """Authentication mode advertised to the UI."""

    NONE = "none"
    API_KEY = "api-key"


class ConfigResponse(BaseModel):
    """Configuration surface exposed to the UI."""

    requires_api_key: bool
    auth_mode: AuthMode
    has_active_session: bool = False


class LoginRequest(BaseModel):
    """Request body for the /login endpoint."""

    api_key: str


class LoginResponse(BaseModel):
    """Response body for the /login endpoint."""

    authenticated: bool
    is_admin: bool


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_session_jwt(*, is_admin: bool) -> str:
    """Mint a signed session JWT. The raw API key is never stored in claims."""
    now = int(time.time())
    payload = {
        "sub": "ac-session",
        "is_admin": is_admin,
        "iat": now,
        "exp": now + SESSION_MAX_AGE_SECONDS,
    }
    return jwt.encode(payload, auth_settings.get_session_secret(), algorithm=JWT_ALGORITHM)


def decode_session_jwt(token: str) -> dict | None:
    """Validate and decode a session JWT. Returns None on any failure."""
    try:
        return jwt.decode(
            token,
            auth_settings.get_session_secret(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "is_admin"]},
        )
