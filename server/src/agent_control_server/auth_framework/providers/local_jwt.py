"""Authorizer that verifies a locally-minted runtime token.

Wired to the runtime resolution path. Reads the runtime token from a
configurable header (``Authorization`` by default), verifies the
signature against the runtime secret, checks the token's scope covers
the requested operation, and returns a :class:`Principal` carrying the
bound target. When a ``context_builder`` on the dependency must surface
matching ``target_type`` / ``target_id`` values for target-bound tokens.

The header is configurable so the server can sit behind a gateway that
reserves ``Authorization`` for its own identity JWT (point the verifier at
a dedicated header to avoid the collision).
"""

from __future__ import annotations

from typing import Any

from agent_control_models.errors import ErrorCode
from fastapi import Request

from ...errors import AuthenticationError, ForbiddenError
from ..core import Operation, Principal, RequestAuthorizer
from ..runtime_token import RuntimeTokenError, verify_runtime_token

DEFAULT_RUNTIME_TOKEN_HEADER = "Authorization"

# RFC 7230 "token" characters, the grammar an HTTP header field name must
# follow. A header name with spaces, colons, control chars, or non-ASCII can't
# be sent by a compliant client, so reject it at config time rather than
# starting with an auth setup that fails on every request.
_HTTP_TOKEN_CHARS = frozenset(
    "!#$%&'*+-.^_`|~0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def validate_http_field_name(name: str) -> str:
    """Return ``name`` if it is a valid HTTP header field name, else raise.

    Kept in sync with the SDK's ``runtime_auth.validate_http_field_name`` so
    both sides reject the same invalid runtime-token headers.
    """
    if not name or any(ch not in _HTTP_TOKEN_CHARS for ch in name):
        raise ValueError(
            "runtime-token header must be a valid HTTP header field name "
            "(RFC 7230 token: letters, digits, and !#$%&'*+-.^_`|~ only, no spaces)."
        )
    return name


