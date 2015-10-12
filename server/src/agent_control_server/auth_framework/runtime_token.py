"""Runtime-token mint and verify helpers.

The runtime auth flow is two-phase:

1. **Exchange.** A target-bearing call presents a long-lived credential
   (e.g., an API key) plus ``(target_type, target_id)``. The server
   forwards the credential to an upstream authorization service which
   either denies the request or returns a normalized grant
   (``actor_id``, ``scopes``, ``target_type``, ``target_id``,
   ``expires_at``). The server then mints a short-lived local token
   stamped with those claims.
2. **Verify.** Subsequent target-bearing calls present the local token
   on the request. The server verifies the signature, the expiry, the
   ``runtime`` domain marker, and the scope; the resolved
   :class:`Principal` carries the bound target.

Token rules:

- Algorithm: HS256.
- Issuer: ``agent-control/server``; verifier: same.
- Signing key: dedicated secret (``AGENT_CONTROL_RUNTIME_TOKEN_SECRET``).
  Never reuse other JWT secrets.
- One token covers one target only.
- ``domain`` claim pins the token to the runtime path; tokens minted
  here MUST not be accepted on management endpoints.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from agent_control_models import JSONObject
from pydantic import TypeAdapter, ValidationError

_ALGORITHM = "HS256"
_ISSUER = "agent-control/server"
_DOMAIN = "runtime"
_JSON_OBJECT_ADAPTER: TypeAdapter[JSONObject] = TypeAdapter(JSONObject)


class RuntimeTokenError(Exception):
    """Raised when a runtime token cannot be verified or minted."""


class UpstreamGrantExpiredError(RuntimeTokenError):
    """Raised when the upstream grant's ``expires_at`` is at or before
    the issuing time, so the resulting token would already be expired.

    Distinct from generic :class:`RuntimeTokenError` so the exchange
    endpoint can surface this as a 502 (upstream returned an unusable
    grant) rather than a 503 (server misconfigured).
    """


@dataclass(frozen=True)
class RuntimeTokenClaims:
    """Fields baked into a runtime token."""

    namespace_key: str
    actor_id: str
    target_type: str
    target_id: str
    scopes: tuple[str, ...]
    expires_at: datetime
    issued_at: datetime
    jti: str
    extensions: JSONObject | None = None


def mint_runtime_token(
    *,
    namespace_key: str,
    actor_id: str,
    target_type: str,
    target_id: str,
    scopes: tuple[str, ...],
    secret: str,
    ttl_seconds: int,
    upstream_expires_at: datetime | None = None,
    extensions: JSONObject | None = None,
    now: datetime | None = None,
) -> tuple[str, RuntimeTokenClaims]:
    """Mint a runtime token. Returns ``(token, claims)``.

    The local token's expiry is the earlier of ``ttl_seconds`` from now
    and ``upstream_expires_at`` (when supplied), so the local lifetime
    can never outlive the upstream grant.
    """
    if not secret:
        raise RuntimeTokenError(
            "Runtime token secret is not configured. Set "
            "AGENT_CONTROL_RUNTIME_TOKEN_SECRET to enable runtime auth."
        )
    if not namespace_key:
        raise RuntimeTokenError("namespace_key is required to mint a runtime token")
    if not actor_id:
        raise RuntimeTokenError("actor_id is required to mint a runtime token")
    if not target_type:
        raise RuntimeTokenError("target_type is required to mint a runtime token")
    if not target_id:
        raise RuntimeTokenError("target_id is required to mint a runtime token")
    if ttl_seconds <= 0:
        raise RuntimeTokenError("ttl_seconds must be positive")
    if upstream_expires_at is not None and (
        upstream_expires_at.tzinfo is None or upstream_expires_at.utcoffset() is None
    ):
        # The HTTP-upstream parser already rejects naive datetimes, but
        # this helper has other call sites (custom authorizers, tests)
        # that can supply a naive value. Comparing it against
        # ``datetime.now(UTC)`` below would raise a raw ``TypeError``;
        # surface the misuse as a typed ``RuntimeTokenError`` instead.
        # Both ``tzinfo`` and ``utcoffset()`` are checked because a
        # custom ``tzinfo`` subclass can set the attribute but return
        # ``None`` from ``utcoffset()``, leaving comparisons broken.
        raise RuntimeTokenError(
            "upstream_expires_at must be timezone-aware "
