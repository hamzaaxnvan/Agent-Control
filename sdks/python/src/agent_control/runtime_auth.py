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


class RuntimeTokenCache:
    """Thread-safe runtime token cache keyed by server and target."""

    def __init__(
        self,
        *,
        max_entries: int = _DEFAULT_MAX_CACHE_ENTRIES,
        jwt_unavailable_ttl_seconds: int = _DEFAULT_JWT_UNAVAILABLE_TTL_SECONDS,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1.")
        if jwt_unavailable_ttl_seconds < 0:
            raise ValueError("jwt_unavailable_ttl_seconds must be >= 0.")
        self._max_entries = max_entries
        self._jwt_unavailable_ttl_seconds = jwt_unavailable_ttl_seconds
        self._tokens: dict[_TokenKey, RuntimeToken] = {}
        self._jwt_unavailable_until: datetime | None = None
        self._jwt_unavailable_servers: dict[str, datetime] = {}
        self._jwt_unavailable_targets: dict[_TokenKey, datetime] = {}
        self._exchange_locks: dict[_LockKey, asyncio.Lock] = {}
        self._lock = threading.Lock()

    def get(
        self,
        server_url: str,
        target_type: str,
        target_id: str,
        *,
        cache_identity: str = "",
        refresh_margin_seconds: int,
    ) -> RuntimeToken | None:
        """Return a fresh cached token for the target, if present."""
        key = (server_url, cache_identity, target_type, target_id)
        with self._lock:
            token = self._tokens.get(key)
            if token is None:
                return None
            if token.is_fresh(refresh_margin_seconds=refresh_margin_seconds):
                return token
            self._tokens.pop(key, None)
            return None

    def set(self, token: RuntimeToken, *, cache_identity: str = "") -> None:
        """Store a token and clear any fallback marker for its target."""
        key = (token.server_url, cache_identity, token.target_type, token.target_id)
        with self._lock:
            if key not in self._tokens and len(self._tokens) >= self._max_entries:
                oldest_key = next(iter(self._tokens))
                self._tokens.pop(oldest_key, None)
                self._jwt_unavailable_targets.pop(oldest_key, None)
            self._tokens[key] = token
            self._jwt_unavailable_servers.pop(token.server_url, None)
            self._jwt_unavailable_targets.pop(key, None)

    def remove(
        self,
        server_url: str,
        target_type: str,
        target_id: str,
        *,
        cache_identity: str = "",
    ) -> None:
        """Drop the cached token for one target."""
        with self._lock:
            self._tokens.pop((server_url, cache_identity, target_type, target_id), None)

    def mark_jwt_unavailable(
        self,
        *,
        server_url: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        cache_identity: str = "",
        globally: bool = False,
        ttl_seconds: int | None = None,
    ) -> None:
        """Record that JWT runtime auth should not be attempted."""
        ttl = self._jwt_unavailable_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl < 0:
            raise ValueError("ttl_seconds must be >= 0.")
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        with self._lock:
