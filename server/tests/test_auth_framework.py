"""Unit tests for the pluggable request-auth framework."""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_control_server.auth_framework.core import (
    Operation,
    Principal,
    clear_authorizers,
    get_authorizer,
    require_operation,
    set_authorizer,
)
from agent_control_server.auth_framework.providers import (
    AccessLevel,
    HeaderAuthProvider,
    HttpUpstreamAuthProvider,
    LocalJwtVerifyProvider,
    NoAuthProvider,
)
from agent_control_server.auth_framework.providers.header import (
    DEFAULT_OPERATION_ACCESS,
)
from agent_control_server.auth_framework.providers.http_upstream import (
    HttpUpstreamConfig,
)
from agent_control_server.config import auth_settings
from agent_control_server.errors import (
    APIError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
)
from agent_control_server.logging_utils import configure_logging
from agent_control_server.models import DEFAULT_NAMESPACE_KEY


def _build_request(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
):
    """Build a minimal Starlette-compatible request mock."""
    request = MagicMock()
    request.headers = headers or {}
    request.cookies = cookies or {}
    return request


def _clear_auth_settings_cache() -> None:
    for attr in (
        "_parsed_api_keys",
        "_parsed_admin_api_keys",
        "_all_valid_keys",
        "_all_admin_keys",
    ):
        auth_settings.__dict__.pop(attr, None)


# 32-byte test secret (HS256 wants >= 32 bytes; shorter raises a warning).
_TEST_SECRET = "test-runtime-secret-12345678901234567890"
_OTHER_SECRET = "other-runtime-secret-1234567890123456789"


# ---------------------------------------------------------------------------
# Coverage of operation -> access-level mapping
# ---------------------------------------------------------------------------


def test_default_operation_access_covers_every_operation():
    """Every Operation member must declare a default access level."""
    missing = [op for op in Operation if op not in DEFAULT_OPERATION_ACCESS]
    assert not missing, f"Operations missing default access mapping: {missing}"


# ---------------------------------------------------------------------------
# NoAuthProvider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_auth_provider_allows_any_operation():
    provider = NoAuthProvider(default_namespace_key="ns-local")

    principal = await provider.authorize(
        _build_request(),
        Operation.CONTROLS_DELETE,
    )

    assert principal == Principal(namespace_key="ns-local")


@pytest.mark.asyncio
async def test_no_auth_provider_grants_runtime_exchange_scope():
    provider = NoAuthProvider()

    principal = await provider.authorize(
        _build_request(),
        Operation.RUNTIME_TOKEN_EXCHANGE,
    )

    assert principal.scopes == (Operation.RUNTIME_USE.value,)


# ---------------------------------------------------------------------------
# HeaderAuthProvider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_header_provider_no_auth_mode_passes_admin_op():
    """When ``api_key_enabled`` is False, even admin operations succeed.

    Preserves the pre-framework behavior where setting the server into
    no-auth mode opens every endpoint regardless of access level.
    """
    provider = HeaderAuthProvider()

    with patch("agent_control_server.auth.auth_settings.api_key_enabled", False):
        principal = await provider.authorize(
            _build_request(),
            Operation.CONTROL_BINDINGS_WRITE,
        )

    assert principal.namespace_key == DEFAULT_NAMESPACE_KEY
    assert principal.is_admin is False


@pytest.mark.asyncio
async def test_header_provider_public_returns_default_namespace():
    provider = HeaderAuthProvider(
        operation_access={Operation.CONTROL_BINDINGS_READ: AccessLevel.PUBLIC}
    )
    principal = await provider.authorize(
        _build_request(),
        Operation.CONTROL_BINDINGS_READ,
    )
    assert principal == Principal(namespace_key=DEFAULT_NAMESPACE_KEY)


@pytest.mark.asyncio
async def test_header_provider_authenticated_calls_local_validator():
    provider = HeaderAuthProvider()
    expected_client = MagicMock(is_admin=False, key_id="abc12345")

    with patch(
        "agent_control_server.auth_framework.providers.header._validate_api_key",
        new=AsyncMock(return_value=expected_client),
    ) as mocked:
        principal = await provider.authorize(
            _build_request(headers={"X-API-Key": "key-123"}),
            Operation.CONTROL_BINDINGS_READ,
        )

    mocked.assert_awaited_once()
    args, kwargs = mocked.await_args
    assert args[0] == "key-123"
    assert kwargs["require_admin"] is False
    assert principal.namespace_key == DEFAULT_NAMESPACE_KEY
    assert principal.is_admin is False
    assert principal.caller_id == "abc12345"


@pytest.mark.asyncio
async def test_header_provider_admin_op_requires_admin():
    provider = HeaderAuthProvider()
    admin_client = MagicMock(is_admin=True, key_id="admin01")

    with patch(
        "agent_control_server.auth_framework.providers.header._validate_api_key",
        new=AsyncMock(return_value=admin_client),
    ) as mocked:
        principal = await provider.authorize(
            _build_request(headers={"X-API-Key": "admin-key"}),
            Operation.CONTROL_BINDINGS_WRITE,
        )

    args, kwargs = mocked.await_args
    assert kwargs["require_admin"] is True
    assert principal.is_admin is True


@pytest.mark.asyncio
async def test_header_provider_v1_ignores_namespace_header():
    """V1 always returns the default namespace regardless of header value."""
    provider = HeaderAuthProvider(
        operation_access={Operation.CONTROL_BINDINGS_READ: AccessLevel.PUBLIC}
    )
    principal = await provider.authorize(
        _build_request(headers={"X-Namespace-Key": "org-foo"}),
        Operation.CONTROL_BINDINGS_READ,
    )
    assert principal.namespace_key == DEFAULT_NAMESPACE_KEY


@pytest.mark.asyncio
async def test_header_provider_unknown_operation_raises():
    provider = HeaderAuthProvider(operation_access={})
    with pytest.raises(RuntimeError, match="No access level"):
        await provider.authorize(
            _build_request(),
            Operation.CONTROL_BINDINGS_READ,
        )


# ---------------------------------------------------------------------------
# HttpUpstreamAuthProvider
# ---------------------------------------------------------------------------


def _build_upstream(
    response_factory,
    *,
    config_overrides: dict[str, Any] | None = None,
) -> HttpUpstreamAuthProvider:
    config_kwargs: dict[str, Any] = {"url": "https://upstream.example/check"}
    if config_overrides:
        config_kwargs.update(config_overrides)
    config = HttpUpstreamConfig(**config_kwargs)

    transport = httpx.MockTransport(response_factory)
    client = httpx.AsyncClient(transport=transport)
    return HttpUpstreamAuthProvider(config, client=client)


def _patch_owned_upstream_client(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    ssl_context = object()

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def aclose(self) -> None:
            captured["closed"] = True

    def fake_create_default_context(*, cafile: str | None = None) -> object:
        captured["cafile"] = cafile
        return ssl_context

    monkeypatch.setattr(
        "agent_control_server.auth_framework.providers.http_upstream.httpx.AsyncClient",
        FakeAsyncClient,
    )
    monkeypatch.setattr(
        "agent_control_server.auth_framework.providers.http_upstream.ssl.create_default_context",
        fake_create_default_context,
    )
    captured["ssl_context"] = ssl_context
    return captured


@pytest.mark.asyncio
async def test_http_upstream_returns_principal_on_200():
    captured: dict[str, Any] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "namespace_key": "org-7",
                "is_admin": True,
                "caller_id": "user-42",
            },
        )

    provider = _build_upstream(factory)
    request = _build_request(headers={"X-API-Key": "caller-key"})
    principal = await provider.authorize(request, Operation.CONTROL_BINDINGS_WRITE)

    assert principal == Principal(namespace_key="org-7", is_admin=True, caller_id="user-42")
    assert captured["url"] == "https://upstream.example/check"
    assert captured["headers"]["x-api-key"] == "caller-key"


@pytest.mark.asyncio
async def test_http_upstream_resolves_identity_at_configured_url():
    captured: dict[str, Any] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "namespace_key": "org-7",
                "caller_id": "user-42",
                "is_admin": True,
                "scopes": ["controls.read"],
            },
        )

    provider = _build_upstream(
        factory,
        config_overrides={
            "url": (
                "https://orbit.example/prefix/internal/auth/agent_control/check_management_access"
            ),
            "identity_url": "https://orbit.example/prefix/internal/auth/resolve_tenant_context",
            "service_token": "service-secret",
            "extra_forward_headers": ("X-Deployer-Auth",),
        },
    )
    assert provider.binding_target_authorization is True
    principal = await provider.resolve_identity(
        _build_request(
            headers={
                "X-API-Key": "caller-key",
                "Authorization": "Bearer caller-token",
                "Cookie": "session=caller-session",
                "X-Deployer-Auth": "deployer-key",
            }
        ),
        Operation.CONTROL_BINDINGS_WRITE,
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "https://orbit.example/prefix/internal/auth/resolve_tenant_context"
    assert captured["headers"]["x-api-key"] == "caller-key"
    assert captured["headers"]["authorization"] == "Bearer caller-token"
    assert captured["headers"]["cookie"] == "session=caller-session"
    assert captured["headers"]["x-deployer-auth"] == "deployer-key"
    assert captured["headers"]["x-agent-control-service-token"] == "service-secret"
    assert principal == Principal(namespace_key="org-7", caller_id="user-42")


@pytest.mark.asyncio
async def test_http_upstream_resolves_identity_at_explicit_url():
    captured: dict[str, str] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"namespace_key": "tenant-1"})

    provider = _build_upstream(
        factory,
        config_overrides={"identity_url": "https://identity.example/resolve"},
    )
    assert provider.binding_target_authorization is True
    principal = await provider.resolve_identity(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert captured["url"] == "https://identity.example/resolve"
    assert principal == Principal(namespace_key="tenant-1")


@pytest.mark.asyncio
async def test_http_upstream_direct_identity_lookup_requires_configured_url():
    provider = _build_upstream(lambda request: pytest.fail("unexpected upstream call"))
    assert provider.binding_target_authorization is False

    with pytest.raises(APIError) as exc_info:
        await provider.resolve_identity(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "AUTH_MISCONFIGURED"


@pytest.mark.asyncio
async def test_http_upstream_identity_preserves_401():
    provider = _build_upstream(
        lambda request: httpx.Response(401),
        config_overrides={"identity_url": "https://identity.example/resolve"},
    )

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.resolve_identity(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 422])
async def test_http_upstream_identity_rejection_reports_sanitized_diagnostics(
    caplog: pytest.LogCaptureFixture,
    status: int,
) -> None:
    # Given: identity resolution rejects a credential, echoing sensitive input.
    sentinel = "SENTINEL-IDENTITY-DO-NOT-LOG"
    provider = _build_upstream(
        lambda request: httpx.Response(
            status,
            json={
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", sentinel],
                        "input": sentinel,
                        "msg": sentinel,
                        "ctx": {"credential": sentinel},
                    }
                ]
            },
        ),
        config_overrides={
            "identity_url": "https://identity.example/resolve",
            "service_token": sentinel,
        },
    )

    # When: resolving identity through the same response handler as authorization.
    with caplog.at_level(logging.WARNING), pytest.raises(APIError) as exc_info:
        await provider.resolve_identity(
            _build_request(
                headers={
                    "X-API-Key": sentinel,
                    "Authorization": f"Bearer {sentinel}",
                    "Cookie": f"session={sentinel}",
                }
            ),
            Operation.CONTROL_BINDINGS_READ,
        )

    # Then: the rejection stays a 502 and logs only safe identity diagnostics.
    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "AUTH_UPSTREAM_REJECTED"
    record = _rejection_record(caplog)
    assert record.__dict__["operation"] == "identity.resolve"
    assert record.__dict__["status_code"] == status
    assert record.__dict__["target_context"] == {"present": "false"}
    assert record.__dict__["upstream_validation"] == {
        "0": {"type": "missing", "loc": "body.<other>"}
    }
    assert record.__dict__["upstream_validation_total"] == 1
    assert record.__dict__["upstream_validation_status"] == "parsed"
    assert sentinel not in record.getMessage()
    assert sentinel not in str(record.__dict__)


@pytest.mark.asyncio
async def test_http_upstream_identity_treats_missing_route_as_upstream_error():
    provider = _build_upstream(
        lambda request: httpx.Response(404),
        config_overrides={"identity_url": "https://identity.example/resolve"},
    )

    with pytest.raises(APIError) as exc_info:
        await provider.resolve_identity(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "AUTH_UPSTREAM_REJECTED"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_http_upstream_identity_fails_closed_when_unavailable(status: int):
    provider = _build_upstream(
        lambda request: httpx.Response(status),
        config_overrides={"identity_url": "https://identity.example/resolve"},
    )

    with pytest.raises(APIError) as exc_info:
        await provider.resolve_identity(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grant",
    [
        {},
        {"namespace_key": ""},
        {"namespace_key": 42},
        {"namespace_key": "tenant-1", "is_admin": "true"},
    ],
)
async def test_http_upstream_identity_rejects_malformed_grant(grant: dict[str, Any]):
    provider = _build_upstream(
        lambda request: httpx.Response(200, json=grant),
        config_overrides={"identity_url": "https://identity.example/resolve"},
    )

    with pytest.raises(APIError) as exc_info:
        await provider.resolve_identity(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_http_upstream_forwards_service_token():
    captured: dict[str, Any] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"namespace_key": "ns"})

    provider = _build_upstream(
        factory,
        config_overrides={
            "service_token": "shh",
            "service_token_header": "X-Custom-Token",
        },
    )
    await provider.authorize(_build_request(), Operation.CONTROL_BINDINGS_READ)

    assert captured["headers"]["x-custom-token"] == "shh"


def test_http_upstream_rejects_service_token_header_collision():
    with pytest.raises(ValueError, match="service_token_header"):
        HttpUpstreamConfig(
            url="https://upstream.example/check",
            service_token="shh",
            service_token_header="Authorization",
        )


def test_http_upstream_rejects_extra_forwarded_service_token_header_collision():
    with pytest.raises(ValueError, match="service_token_header"):
        HttpUpstreamConfig(
            url="https://upstream.example/check",
            service_token="shh",
            service_token_header="X-Custom-Auth",
            extra_forward_headers=("x-custom-auth",),
        )


@pytest.mark.parametrize(
    "config_overrides, match",
    [
        ({"keepalive_expiry_seconds": -0.1}, "keepalive_expiry_seconds"),
        ({"max_connections": 0}, "max_connections"),
        ({"max_keepalive_connections": -1}, "max_keepalive_connections"),
        (
            {"max_connections": 2, "max_keepalive_connections": 3},
            "max_keepalive_connections",
        ),
    ],
)
def test_http_upstream_rejects_invalid_connection_tuning(config_overrides, match):
    with pytest.raises(ValueError, match=match):
        HttpUpstreamConfig(
            url="https://upstream.example/check",
            **config_overrides,
        )


@pytest.mark.asyncio
async def test_http_upstream_uses_ca_file_for_owned_client(monkeypatch):
    captured = _patch_owned_upstream_client(monkeypatch)

    provider = HttpUpstreamAuthProvider(
        HttpUpstreamConfig(
            url="https://upstream.example/check",
            timeout_seconds=2.5,
            ca_file="/etc/agent-control/auth-upstream-ca/ca.crt",
        )
    )

    await provider.aclose()

    assert captured["timeout"] == 2.5
    assert "limits" in captured
    assert captured["cafile"] == "/etc/agent-control/auth-upstream-ca/ca.crt"
    assert captured["verify"] is captured["ssl_context"]
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_http_upstream_uses_connection_limits_for_owned_client(monkeypatch):
    captured = _patch_owned_upstream_client(monkeypatch)

    provider = HttpUpstreamAuthProvider(
        HttpUpstreamConfig(
            url="https://upstream.example/check",
            keepalive_expiry_seconds=0.5,
            max_connections=7,
            max_keepalive_connections=2,
        )
    )

    await provider.aclose()

    assert "limits" in captured
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_http_upstream_forwards_extra_headers():
    # Given: a provider configured with an extra header in its forward list
    captured: dict[str, Any] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"namespace_key": "ns"})

    provider = _build_upstream(
        factory,
        config_overrides={"extra_forward_headers": ("X-Deployer-Auth",)},
    )

    # When: the inbound request carries the extra header
    inbound = _build_request(headers={"X-Deployer-Auth": "k_abc", "X-API-Key": "k1"})
    await provider.authorize(inbound, Operation.CONTROL_BINDINGS_READ)

    # Then: both the default and the extra header reach the upstream
    assert captured["headers"]["x-deployer-auth"] == "k_abc"
    assert captured["headers"]["x-api-key"] == "k1"


@pytest.mark.asyncio
async def test_http_upstream_default_forward_set_unchanged():
    # Given: a provider with no extra_forward_headers
    captured: dict[str, Any] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"namespace_key": "ns"})

    provider = _build_upstream(factory)

    # When: the inbound carries an unlisted header alongside a default one
    inbound = _build_request(
        headers={"X-API-Key": "k1", "X-Deployer-Auth": "should-not-forward"}
    )
    await provider.authorize(inbound, Operation.CONTROL_BINDINGS_READ)

    # Then: only the default-set header reaches the upstream
    assert captured["headers"].get("x-api-key") == "k1"
    assert "x-deployer-auth" not in captured["headers"]


@pytest.mark.asyncio
async def test_http_upstream_extra_forward_dedupes_against_defaults():
    # Given: extra list duplicates a default header (different case)
    captured: dict[str, Any] = {}

    def factory(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"namespace_key": "ns"})

    provider = _build_upstream(
        factory,
        config_overrides={"extra_forward_headers": ("x-api-key", "Authorization")},
    )

    # When: inbound has both
    inbound = _build_request(headers={"X-API-Key": "k1", "Authorization": "Bearer t"})
    await provider.authorize(inbound, Operation.CONTROL_BINDINGS_READ)

    # Then: each header appears exactly once on the upstream request
    forwarded = captured["headers"]
    assert sum(1 for k in forwarded if k.lower() == "x-api-key") == 1
    assert sum(1 for k in forwarded if k.lower() == "authorization") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, expected",
    [
        (401, AuthenticationError),
        (403, ForbiddenError),
        (404, NotFoundError),
    ],
)
async def test_http_upstream_maps_client_errors(status, expected):
    provider = _build_upstream(lambda req: httpx.Response(status))
    with pytest.raises(expected):
        await provider.authorize(_build_request(), Operation.CONTROL_BINDINGS_WRITE)


@pytest.mark.asyncio
async def test_http_upstream_fails_closed_on_5xx():
    provider = _build_upstream(lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(APIError) as exc_info:
        await provider.authorize(_build_request(), Operation.CONTROL_BINDINGS_WRITE)
    assert exc_info.value.status_code == 503
    # Status is named in the detail so operators can distinguish the
    # catch-all path from the rate-limit branch below.
    assert "500" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 422])
async def test_http_upstream_unexpected_4xx_reports_upstream_rejection(status):
    """Unexpected upstream 4xx responses retain the contract failure signal."""
    provider = _build_upstream(lambda req: httpx.Response(status, text="bad request"))

    with pytest.raises(APIError) as exc_info:
        await provider.authorize(_build_request(), Operation.CONTROL_BINDINGS_WRITE)

    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "AUTH_UPSTREAM_REJECTED"
    assert str(status) in exc_info.value.detail
    assert "request shape" in exc_info.value.hint


def _rejection_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """Return the upstream-rejection warning emitted by the 4xx branch."""
    records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("Authorization upstream rejected operation")
    ]
    assert records
    return records[-1]


@pytest.mark.asyncio
async def test_http_upstream_4xx_diagnostics_name_the_rejected_field(
    caplog: pytest.LogCaptureFixture,
):
    """A 422 names the upstream field path and error kind, not the value.

    This is the case the multitenant incident could not diagnose: the log
    recorded only the operation and status, so the rejected field was unknown.
    """
    provider = _build_upstream(
        lambda req: httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "type": "uuid_parsing",
                        "loc": ["body", "context", "target_id"],
                        "msg": "Input should be a valid UUID",
                        "input": "not-a-uuid",
                    }
                ]
            },
        )
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(APIError):
            await provider.authorize(
                _build_request(),
                Operation.RUNTIME_TOKEN_EXCHANGE,
                context={"target_type": "log_stream", "target_id": "not-a-uuid"},
            )

    record = _rejection_record(caplog)
    assert record.__dict__["operation"] == Operation.RUNTIME_TOKEN_EXCHANGE.value
    assert record.__dict__["status_code"] == 422
    assert record.__dict__["upstream_validation"] == {
        "0": {"type": "uuid_parsing", "loc": "body.context.target_id"}
    }
    assert record.__dict__["upstream_validation_total"] == 1
    assert record.__dict__["upstream_validation_status"] == "parsed"
    assert record.__dict__["target_context"] == {
        "present": "true",
        "target_type": "string:len=10",
        "target_id": "string:len=10",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context", "expected_shape"),
    [
        (None, {"present": "false"}),
        ({}, {"present": "false"}),
        (
            {"target_type": "log_stream"},
            {"present": "true", "target_type": "string:len=10", "target_id": "missing"},
        ),
        (
            {"target_type": None, "target_id": None},
            {"present": "true", "target_type": "null", "target_id": "null"},
        ),
        (
            {"target_type": "log_stream", "target_id": ""},
            {"present": "true", "target_type": "string:len=10", "target_id": "empty"},
        ),
        (
            {"target_type": "log_stream", "target_id": 42},
            {
                "present": "true",
                "target_type": "string:len=10",
                "target_id": "non_string:int",
            },
        ),
    ],
)
async def test_http_upstream_4xx_diagnostics_report_target_context_shape(
    caplog: pytest.LogCaptureFixture,
    context: dict[str, object] | None,
    expected_shape: dict[str, str],
):
    """Target context is described by shape, so absent and null stay distinct."""
    sent_payloads: list[dict[str, object]] = []

    def reject(request: httpx.Request) -> httpx.Response:
        sent_payloads.append(json.loads(request.content))
        return httpx.Response(422, text="rejected")

    provider = _build_upstream(reject)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(APIError):
            await provider.authorize(
                _build_request(),
                Operation.RUNTIME_TOKEN_EXCHANGE,
                context=context,
            )

    assert _rejection_record(caplog).__dict__["target_context"] == expected_shape
    assert ("context" in sent_payloads[0]) is bool(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
async def test_http_upstream_4xx_diagnostics_reach_configured_log_output(
    monkeypatch: pytest.MonkeyPatch,
    as_json: bool,
) -> None:
    """The configured handler must emit the fields, not only retain them in LogRecord."""
    sentinel = "SENTINEL-DO-NOT-LOG"
    provider = _build_upstream(
        lambda req: httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "type": "uuid_parsing",
                        "loc": ["body", "context", "target_id"],
                        "msg": sentinel,
                        "input": sentinel,
                    }
                ]
            },
        )
    )
    monkeypatch.setenv("AGENT_CONTROL_CONFIGURE_LOGGING", "true")
    root = logging.getLogger()
    original_root = (list(root.handlers), root.level)
    uvicorn_loggers = [
        logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    ]
    original_uvicorn = [
        (logger, list(logger.handlers), logger.level, logger.propagate)
        for logger in uvicorn_loggers
    ]
    stream = io.StringIO()
    try:
        configure_logging(level="WARNING", json=as_json)
        root.handlers[0].setStream(stream)
        with pytest.raises(APIError):
            await provider.authorize(
                _build_request(),
                Operation.RUNTIME_TOKEN_EXCHANGE,
                context={"target_type": "log_stream", "target_id": sentinel},
            )
    finally:
        root.handlers, root.level = original_root
        for logger, handlers, level, propagate in original_uvicorn:
            logger.handlers, logger.level, logger.propagate = handlers, level, propagate

    output = stream.getvalue()
    assert sentinel not in output
    if as_json:
        rendered = json.loads(output)
        assert rendered["target_context"]["target_id"] == f"string:len={len(sentinel)}"
        assert rendered["upstream_validation"] == {
            "0": {"type": "uuid_parsing", "loc": "body.context.target_id"}
        }
        assert rendered["upstream_validation_total"] == 1
        assert rendered["upstream_validation_status"] == "parsed"
    else:
        assert 'target_context={"present":"true"' in output
        assert 'upstream_validation={"0":{"type":"uuid_parsing"' in output
        assert "upstream_validation_total=1" in output
        assert "upstream_validation_status=parsed" in output


@pytest.mark.asyncio
