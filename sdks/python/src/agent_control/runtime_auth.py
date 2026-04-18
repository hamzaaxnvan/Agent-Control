"""Runtime-token cache helpers for the Agent Control SDK."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

RuntimeAuthMode = Literal["auto", "none", "api_key", "jwt"]

_TokenKey = tuple[str, str, str, str]
_LockKey = tuple[str, str, str, str, asyncio.AbstractEventLoop]
_DEFAULT_MAX_CACHE_ENTRIES = 256
_DEFAULT_JWT_UNAVAILABLE_TTL_SECONDS = 30

DEFAULT_RUNTIME_TOKEN_HEADER = "Authorization"

# RFC 7230 "token" characters, the grammar an HTTP header field name must
# follow. Anything outside this set (spaces, colons, control chars, non-ASCII)
# produces a header a compliant client or gateway cannot send, so reject it up
# front rather than failing at request time.
_HTTP_TOKEN_CHARS = frozenset(
    "!#$%&'*+-.^_`|~0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def validate_http_field_name(name: str, *, field: str = "runtime_token_header") -> str:
    """Validate ``name`` against the RFC 7230 header field-name grammar.

    Returns the name unchanged when valid; raises ``ValueError`` otherwise.
    Keeps the SDK and server rejecting the same set of invalid headers.
    """
    if not name or any(ch not in _HTTP_TOKEN_CHARS for ch in name):
        raise ValueError(
            f"{field} must be a valid HTTP header field name "
            "(RFC 7230 token: letters, digits, and !#$%&'*+-.^_`|~ only, no spaces)."
        )
    return name


def resolve_runtime_token_header(
    value: str | None,
    env_value: str | None,
    *,
    default: str = DEFAULT_RUNTIME_TOKEN_HEADER,
) -> str:
    """Resolve and validate the runtime-token header (param > env > default).

    An explicitly-passed blank ``value`` is a hard error; a blank env value
    falls back to the default. The resolved header is validated against the
    HTTP field-name grammar so misconfiguration is caught before it is used.
    """
    if value is not None and not value.strip():
        raise ValueError("runtime_token_header must not be blank.")
    if env_value is not None and not env_value.strip():
        env_value = None
    resolved = (value or env_value or default).strip()
    return validate_http_field_name(resolved)


@dataclass(frozen=True)
class RuntimeToken:
    """Short-lived runtime token bound to one target."""

    token: str = field(repr=False)
    expires_at: datetime
    server_url: str
    target_type: str
    target_id: str
    scopes: tuple[str, ...]

    def is_fresh(self, *, refresh_margin_seconds: int) -> bool:
        """Return whether the token is usable beyond the refresh margin."""
        refresh_at = datetime.now(UTC) + timedelta(seconds=refresh_margin_seconds)
        return self.expires_at > refresh_at


