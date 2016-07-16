"""Generic primitives for the pluggable request-auth framework.

This module is intentionally provider-neutral: no upstream-specific
nouns, no transport assumptions, no policy engine references.
Providers wire those concerns in
:mod:`agent_control_server.auth_framework.providers`.

Concepts:

- :class:`Operation` is the vocabulary endpoints declare. Adding a new
  endpoint that needs a new permission means adding a member here, not
  changing every provider.
- :class:`Principal` is the resolved-identity result of authorization:
  the namespace the request runs in plus optional caller metadata.
- :class:`RequestAuthorizer` is the seam. Implementations decide whether
  a request may perform an operation; failure raises an HTTP-typed
  error and short-circuits the request.
- :func:`require_operation` is the FastAPI dependency factory endpoints
  attach to. It looks up the active authorizer, builds an optional
  per-request context, and returns the :class:`Principal`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from agent_control_models import JSONObject
from fastapi import Request


class Operation(StrEnum):
    """Authorization vocabulary spoken on the endpoint side.

    Members are stable wire identifiers; providers map them to whatever
    permission system a deployment uses.
    """

    # Control bindings (target attachments).
    CONTROL_BINDINGS_READ = "control_bindings.read"
    CONTROL_BINDINGS_WRITE = "control_bindings.write"

    # Runtime token exchange - wired on the exchange endpoint.
    RUNTIME_TOKEN_EXCHANGE = "runtime.token_exchange"

    CONTROLS_READ = "controls.read"
    CONTROLS_CREATE = "controls.create"
    CONTROLS_UPDATE = "controls.update"
    CONTROLS_DELETE = "controls.delete"
    POLICIES_READ = "policies.read"
    POLICIES_CREATE = "policies.create"
    POLICIES_UPDATE = "policies.update"
    AGENTS_READ = "agents.read"
    AGENTS_CREATE = "agents.create"
    AGENTS_UPDATE = "agents.update"
    EVALUATORS_READ = "evaluators.read"
    OBSERVABILITY_READ = "observability.read"
    OBSERVABILITY_WRITE = "observability.write"
    RUNTIME_USE = "runtime.use"


@dataclass(frozen=True)
class Principal:
    """Resolved identity for an authorized request.

    Attributes:
        namespace_key: The namespace the request runs in. Endpoints use
            this to scope every read and write.
        is_admin: Whether the caller has admin privileges in the
            current namespace.
