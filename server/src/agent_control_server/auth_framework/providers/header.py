"""Default :class:`RequestAuthorizer` that uses local credentials only.

Returns ``DEFAULT_NAMESPACE_KEY`` and enforces a per-operation access
level using the local API-key + session-cookie credential check from
:mod:`agent_control_server.auth`:

- ``ADMIN`` operations require an admin key (or admin session).
- ``AUTHENTICATED`` operations require any valid credential.
- ``PUBLIC`` operations are open.
- When the underlying local credential layer is disabled, every
  operation succeeds with a non-admin :class:`Principal`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import Request

from ...auth import _validate_api_key
from ...models import DEFAULT_NAMESPACE_KEY
from ..core import Operation, Principal, RequestAuthorizer


class AccessLevel(Enum):
    """Access level required for an operation under the local-credential path."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"


# Single source of truth for the local-credential access policy. Adding
# a new :class:`Operation` here makes its required access level
# explicit and auditable; missing entries are rejected at startup so
# wiring drift is loud, not silent.
DEFAULT_OPERATION_ACCESS: dict[Operation, AccessLevel] = {
    Operation.CONTROL_BINDINGS_READ: AccessLevel.AUTHENTICATED,
    Operation.CONTROL_BINDINGS_WRITE: AccessLevel.ADMIN,
    Operation.CONTROLS_READ: AccessLevel.AUTHENTICATED,
    Operation.CONTROLS_CREATE: AccessLevel.ADMIN,
    Operation.CONTROLS_UPDATE: AccessLevel.ADMIN,
    Operation.CONTROLS_DELETE: AccessLevel.ADMIN,
    Operation.POLICIES_READ: AccessLevel.AUTHENTICATED,
    Operation.POLICIES_CREATE: AccessLevel.ADMIN,
    Operation.POLICIES_UPDATE: AccessLevel.ADMIN,
