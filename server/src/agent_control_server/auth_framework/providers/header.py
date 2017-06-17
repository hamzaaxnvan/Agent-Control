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
