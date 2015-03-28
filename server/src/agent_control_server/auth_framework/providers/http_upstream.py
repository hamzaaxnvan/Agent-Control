"""Forwards authorization decisions to a configurable upstream HTTP service.

Used by deployments that already have an authorization service of
record. The provider is generic: it speaks a small JSON protocol to a
single configurable URL, forwards the caller's credentials so the
upstream can identify them, and maps the upstream's HTTP status onto
the matching error.

Wire protocol
-------------

Request (POST to ``upstream_url``):

.. code-block:: json

    {
        "operation": "control_bindings.write",
        "context": { "...optional path params..." }
    }

with the caller's credentials forwarded as request headers (the
provider sets ``X-API-Key``, ``Authorization``, and the ``Cookie``
header from the inbound request) plus an optional service-to-service
token header for upstream→authorization-service trust.

Response (200): JSON object

.. code-block:: json

    {
        "namespace_key": "...",
        "is_admin": false,
        "caller_id": "..."
    }

Statuses other than 200 / 401 / 403 / 404 / 429 fail closed. Unexpected
upstream 4xx responses are reported separately from Agent Control
misconfiguration so operators can distinguish upstream request rejection
from local auth setup failures.
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Literal, TypedDict

import httpx
from agent_control_models import JSONObject
from agent_control_models.errors import ErrorCode, ErrorReason
from fastapi import Request
from prometheus_client import Counter, Histogram
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from ...errors import APIError, AuthenticationError, ForbiddenError, NotFoundError
from ...logging_utils import get_logger
from ..core import Operation, Principal, RequestAuthorizer

_logger = get_logger(__name__)

_DEFAULT_FORWARDED_HEADERS = ("X-API-Key", "Authorization", "Cookie")
# Diagnostic label only; the identity POST has no operation payload.
_IDENTITY_LOOKUP_LABEL = "identity.resolve"

_AUTH_UPSTREAM_ATTEMPTS = Counter(
    "agent_control_server_auth_upstream_attempts_total",
    "Auth upstream HTTP attempts made by Agent Control.",
    ("operation", "outcome", "status_code", "error_type"),
)
_AUTH_UPSTREAM_ATTEMPT_DURATION = Histogram(
    "agent_control_server_auth_upstream_attempt_duration_seconds",
    "Duration of auth upstream HTTP attempts made by Agent Control.",
    ("operation", "outcome"),
)
_JSON_OBJECT_ADAPTER: TypeAdapter[JSONObject] = TypeAdapter(JSONObject)

# Upstream rejection bodies can be arbitrarily long. Bound decoding as well as
# logged output, and report the total when a parsed list is truncated.
_MAX_VALIDATION_RESPONSE_BYTES = 64 * 1024
_MAX_LOGGED_VALIDATION_ERRORS = 5
_MAX_LOGGED_LOCATION_PARTS = 4
_UNKNOWN_VALIDATION_TOTAL: Literal["unknown"] = "unknown"
_SAFE_VALIDATION_LOCATION_PARTS = frozenset(
    {"body", "context", "operation", "target_type", "target_id"}
)
_SAFE_VALIDATION_TYPES = frozenset(
    {"enum", "literal_error", "missing", "string_type", "uuid_parsing", "uuid_type", "uuid_version"}
)
_MISSING = object()


class _ValidationDiagnostic(TypedDict):
    type: str
    loc: str


class _ValidationSummary(TypedDict):
    total: int | Literal["unknown"]
    errors: list[_ValidationDiagnostic]
    status: Literal["parsed", "oversized", "unusable"]


def _field_shape(value: Any) -> str:
    """Classify a target-context field without revealing its value.

    Target identifiers are caller data, so diagnostics carry only the kind of
    value supplied. The length is included because whether an id was
    UUID-shaped is the question these diagnostics exist to answer.
    """
    if value is _MISSING:
        return "missing"
    if value is None:
        return "null"
    if not isinstance(value, str):
        return f"non_string:{type(value).__name__}"
    if not value:
        return "empty"
    return f"string:len={len(value)}"


def _target_context_shape(context: dict[str, Any] | None) -> dict[str, str]:
    """Describe the target context passed to the upstream, values omitted."""
