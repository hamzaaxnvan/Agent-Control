"""Base HTTP client for Agent Control server communication."""

import hashlib
import logging
import os
from collections.abc import Generator
from types import TracebackType
from typing import Any, cast

import httpx

from . import __version__ as sdk_version
from .runtime_auth import (
    RuntimeAuthMode,
    RuntimeTokenCache,
    normalize_runtime_auth_mode,
    parse_runtime_token_exchange_response,
    resolve_runtime_token_header,
)

_logger = logging.getLogger(__name__)

_RUNTIME_AUTH_MODE_ENV_VAR = "AGENT_CONTROL_RUNTIME_AUTH_MODE"
_RUNTIME_TOKEN_HEADER_ENV_VAR = "AGENT_CONTROL_RUNTIME_TOKEN_HEADER"
_DEFAULT_RUNTIME_TOKEN_HEADER = "Authorization"
_DEFAULT_RUNTIME_TOKEN_REFRESH_MARGIN_SECONDS = 30
_AUTO_RUNTIME_TOKEN_FALLBACK_STATUSES = {404, 500, 502, 503, 504}
_GLOBAL_RUNTIME_TOKEN_FALLBACK_STATUSES = {404}


def _runtime_cache_identity(api_key: str | None, api_key_header: str) -> str:
    """Return a stable cache identity without storing the raw credential."""
    normalized_header = api_key_header.lower()
    if not api_key:
        return f"api_key:{normalized_header}:anonymous"
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"api_key:{normalized_header}:{digest}"


class _AgentControlAuth(httpx.Auth):
    """Attach local API-key credentials unless the request already carries them.

    The API key is suppressed only when the request already presents a bearer
    credential on ``Authorization`` or already carries the API key on its own
    header. When the runtime token rides a dedicated header, the API key is
    left in place: it may be the outer credential the request needs to
    authenticate at a gateway before Agent Control verifies the runtime token,
    and it rides a different header so there is no collision.
    """

    def __init__(
        self,
        api_key: str | None,
        header_name: str = "X-API-Key",
    ) -> None:
        self._api_key = api_key
        self._header_name = header_name

    def auth_flow(
        self,
        request: httpx.Request,
    ) -> Generator[httpx.Request, httpx.Response, None]:
        if (
            self._api_key
            and "Authorization" not in request.headers
            and self._header_name not in request.headers
        ):
            request.headers[self._header_name] = self._api_key
        yield request


class AgentControlClient:
    """
    Async HTTP client for Agent Control server.

    This is the base client that provides the HTTP connection management.
    Specific operations are organized into separate modules:
    agents, policies, controls, evaluation.

    Authentication:
        The client supports API key authentication. By default the key is
        sent on the ``X-API-Key`` header; set ``api_key_header`` (or the
        ``AGENT_CONTROL_API_KEY_HEADER`` environment variable) to override.
        API key can be provided:
        1. Directly via the `api_key` parameter
        2. Via the AGENT_CONTROL_API_KEY environment variable

    Usage:
        # Explicit API key
        async with AgentControlClient(api_key="my-secret-key") as client:
            await client.health_check()

        # From environment variable
        os.environ["AGENT_CONTROL_API_KEY"] = "my-secret-key"
        async with AgentControlClient() as client:
            await client.health_check()

        # Custom header name (e.g., when the upstream auth expects something
        # other than X-API-Key). The header name applies to every request
        # this client sends.
        async with AgentControlClient(
            api_key="my-secret-key", api_key_header="X-Custom-API-Key"
        ) as client:
            await client.health_check()
    """

    # Environment variable name for API key
    API_KEY_ENV_VAR = "AGENT_CONTROL_API_KEY"
    API_KEY_HEADER_ENV_VAR = "AGENT_CONTROL_API_KEY_HEADER"
    DEFAULT_API_KEY_HEADER = "X-API-Key"
    BASE_URL_ENV_VAR = "AGENT_CONTROL_URL"

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        api_key: str | None = None,
        api_key_header: str | None = None,
        runtime_auth_mode: RuntimeAuthMode | str | None = None,
        runtime_token_cache: RuntimeTokenCache | None = None,
        runtime_token_refresh_margin_seconds: int = (_DEFAULT_RUNTIME_TOKEN_REFRESH_MARGIN_SECONDS),
        transport: httpx.AsyncBaseTransport | None = None,
        runtime_token_header: str | None = None,
    ):
        """
        Initialize the client.

        Args:
            base_url: Base URL of the Agent Control server. If not provided,
                AGENT_CONTROL_URL is used, falling back to http://localhost:8000.
            timeout: Request timeout in seconds
            api_key: API key for authentication. If not provided, will attempt
                     to read from AGENT_CONTROL_API_KEY environment variable.
            api_key_header: HTTP header name to send the API key on. Defaults
                     to ``X-API-Key``; the AGENT_CONTROL_API_KEY_HEADER
                     environment variable overrides the default. Useful when
                     the configured upstream auth expects a different header.
            runtime_auth_mode: Runtime auth mode for evaluation requests. ``auto``
                attempts target-bound JWT exchange and falls back to normal
                request auth when the exchange endpoint is unavailable. ``jwt``
                requires a successful exchange. ``api_key`` and ``none`` keep
                evaluation requests on the normal request-auth path.
            runtime_token_cache: Optional cache shared across client instances.
            runtime_token_refresh_margin_seconds: Refresh cached runtime tokens
                before this many seconds of validity remain.
            transport: Optional httpx transport, primarily for tests.
            runtime_token_header: HTTP header the runtime token is sent on.
                Defaults to ``Authorization``; the
                AGENT_CONTROL_RUNTIME_TOKEN_HEADER environment variable
                overrides the default. Point this at a dedicated header (e.g.
                ``X-Agent-Control-Runtime-Token``) when the server runs behind
                a gateway that reserves ``Authorization`` for its own identity
                JWT. The server must be configured to read the same header.
        """
        resolved_base_url = base_url or os.environ.get(
            self.BASE_URL_ENV_VAR, "http://localhost:8000"
        )
        self.base_url = resolved_base_url.rstrip("/")
        self.timeout = timeout
        self._api_key = api_key or os.environ.get(self.API_KEY_ENV_VAR)
        self._api_key_header = (
            api_key_header
            or os.environ.get(self.API_KEY_HEADER_ENV_VAR)
            or self.DEFAULT_API_KEY_HEADER
        )
        self._runtime_cache_identity = _runtime_cache_identity(self._api_key, self._api_key_header)
        configured_runtime_mode = runtime_auth_mode or os.environ.get(_RUNTIME_AUTH_MODE_ENV_VAR)
        self._runtime_auth_mode = normalize_runtime_auth_mode(configured_runtime_mode)
        # Explicit blank param is a hard error; a blank env var falls back to
        # the default (mirrors the server's _resolve_runtime_token_header).
        self._runtime_token_header = resolve_runtime_token_header(
            runtime_token_header,
            os.environ.get(_RUNTIME_TOKEN_HEADER_ENV_VAR),
            default=_DEFAULT_RUNTIME_TOKEN_HEADER,
        )
        # Bearer only on Authorization; a dedicated header carries the raw token
        # so it can't collide with the gateway's Authorization JWT. Must stay in
        # sync with LocalJwtVerifyProvider._require_bearer on the server.
        self._runtime_token_use_bearer = (
            self._runtime_token_header.lower() == _DEFAULT_RUNTIME_TOKEN_HEADER.lower()
        )
        if runtime_token_refresh_margin_seconds < 0:
            raise ValueError("runtime_token_refresh_margin_seconds must be >= 0.")
