"""Integration tests for the runtime token exchange endpoint.

These tests cover the request shape, the runtime-secret guard, and the
end-to-end exchange-then-verify path: a token minted via
``POST /api/v1/auth/runtime-token-exchange`` is verified by
``LocalJwtVerifyProvider`` and yields a target-bound :class:`Principal`.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from agent_control_server.auth_framework import Operation, Principal
from agent_control_server.auth_framework.config import (
    RuntimeAuthConfig,
    set_runtime_auth_config,
)
from agent_control_server.auth_framework.core import (
    clear_authorizers,
    set_authorizer,
)
from agent_control_server.auth_framework.providers import HttpUpstreamAuthProvider, LocalJwtVerifyProvider
from agent_control_server.auth_framework.providers.http_upstream import HttpUpstreamConfig
from agent_control_server.auth_framework.runtime_token import RuntimeTokenError

_TEST_SECRET = "test-runtime-secret-12345678901234567890"
_CUSTOM_TARGET_TYPE = "custom_target"


@pytest.fixture
def runtime_config_enabled():
    """Install a deterministic runtime-auth config for the test, then clear."""
    set_runtime_auth_config(RuntimeAuthConfig(secret=_TEST_SECRET, ttl_seconds=300))
    try:
        yield
    finally:
        set_runtime_auth_config(None)


class _StubExchangeAuthorizer:
    """Stand-in for HttpUpstreamAuthProvider.

    Returns a Principal with the grant fields the exchange endpoint
    needs (target binding, scopes, expiry) so the unit test can run
    without a real upstream.
    """

    def __init__(
        self,
        *,
        actor_id: str | None = "actor-x",
        scopes: tuple[str, ...] = ("runtime.use",),
        target_type: str | None = None,
        target_id: str | None = None,
        grant_expires_at: datetime | None = None,
    ) -> None:
        self._actor_id = actor_id
        self._scopes = scopes
        self._target_type = target_type
        self._target_id = target_id
        self._grant_expires_at = grant_expires_at
        self.calls: list[dict[str, object]] = []

    async def authorize(self, request, operation, context=None):
        self.calls.append({"operation": operation, "context": context})
        return Principal(
            namespace_key="default",
            caller_id=self._actor_id,
            target_type=self._target_type,
            target_id=self._target_id,
            scopes=self._scopes,
            grant_expires_at=self._grant_expires_at,
        )


def test_exchange_endpoint_503_when_secret_not_configured(client: TestClient):
    response = client.post(
        "/api/v1/auth/runtime-token-exchange",
        json={"target_type": "log_stream", "target_id": "ls-1"},
    )
    assert response.status_code == 503


@pytest.mark.parametrize(
    "scopes",
    [
        pytest.param(("runtime.use",), id="required-scope"),
        pytest.param(("runtime.use", "runtime.debug"), id="multiple-scopes"),
    ],
)
def test_exchange_endpoint_mints_token_when_configured(
    client: TestClient,
    runtime_config_enabled,
    scopes: tuple[str, ...],
):
    stub = _StubExchangeAuthorizer(
        actor_id="actor-9",
        scopes=scopes,
        target_type="log_stream",
        target_id="ls-42",
        grant_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    clear_authorizers()
    set_authorizer(stub)

    response = client.post(
        "/api/v1/auth/runtime-token-exchange",
        json={"target_type": "log_stream", "target_id": "ls-42"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_type"] == "log_stream"
    assert body["target_id"] == "ls-42"
    assert body["scopes"] == list(scopes)
    assert body["token"]
    assert body["expires_at"]


@pytest.mark.asyncio
async def test_upstream_extensions_round_trip_through_signed_runtime_token(
    runtime_config_enabled,
):
    from agent_control_server.endpoints.auth import (
        RuntimeTokenExchangeRequest,
        runtime_token_exchange,
    )

    trusted_metadata = {"provider_field": "opaque_value", "nested": {"opaque": "value"}}

    def authz_response(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "namespace_key": "namespace-1",
                "caller_id": "opaque-caller",
                "target_type": "custom_target",
                "target_id": "target-9",
                "scopes": ["runtime.use"],
                **trusted_metadata,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(authz_response)) as client:
        provider = HttpUpstreamAuthProvider(
            HttpUpstreamConfig(url="https://authz.test/check"), client=client
        )
        upstream_request = Request(
            {"type": "http", "headers": [], "method": "POST", "path": "/"}
        )
        principal = await provider.authorize(
            upstream_request,
            Operation.RUNTIME_TOKEN_EXCHANGE,
            context={"target_type": "custom_target", "target_id": "target-9"},
        )

    assert principal.extensions == trusted_metadata
    response = await runtime_token_exchange(
        RuntimeTokenExchangeRequest(target_type="custom_target", target_id="target-9"),
        principal=principal,
    )
    token_payload = jwt.decode(
        response.token,
        _TEST_SECRET,
        algorithms=["HS256"],
        issuer="agent-control/server",
    )
    assert "provider_field" not in token_payload
    assert token_payload["extensions"] == trusted_metadata

    verify_request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {response.token}".encode())],
            "method": "POST",
            "path": "/",
        }
    )
    verified_principal = await LocalJwtVerifyProvider(secret=_TEST_SECRET).authorize(
        verify_request,
        Operation.RUNTIME_USE,
            context={"target_type": "custom_target", "target_id": "target-9"},
    )
    assert verified_principal.extensions == trusted_metadata


@pytest.mark.parametrize(
    ("actor_id", "expected_log_actor_id"),
    [
        ("user@example.test", "user@example.test"),
        (None, "anonymous"),
    ],
)
def test_exchange_audit_log_redacts_actor_id(
    client: TestClient,
    runtime_config_enabled,
    caplog: pytest.LogCaptureFixture,
    actor_id: str | None,
    expected_log_actor_id: str,
):
    stub = _StubExchangeAuthorizer(
        actor_id=actor_id,
        scopes=("runtime.use",),
        target_type="log_stream",
        target_id="ls-42",
    )
    clear_authorizers()
    set_authorizer(stub)

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/auth/runtime-token-exchange",
            json={"target_type": "log_stream", "target_id": "ls-42"},
        )

    assert response.status_code == 200, response.text
    records = [
        record
        for record in caplog.records
        if record.getMessage() == "Runtime token exchanged"
    ]
    assert records
    record = records[-1]
    assert "actor_id" not in record.__dict__
    expected_hash = hashlib.sha256(expected_log_actor_id.encode("utf-8")).hexdigest()[:16]
    assert record.__dict__["actor_id_hash"] == expected_hash


@pytest.mark.parametrize(
    (
        "authorized_target_type",
        "authorized_target_id",
        "requested_target_type",
        "requested_target_id",
        "expected_detail",
    ),
    [
        (
            "log_stream",
            "target-1",
            _CUSTOM_TARGET_TYPE,
            "target-1",
            "Authorized target_type does not match the requested target_type.",
        ),
        (
            "log_stream",
            "target-1",
            "log_stream",
            "target-2",
            "Authorized target_id does not match the requested target_id.",
        ),
    ],
)
def test_exchange_endpoint_rejects_target_mismatch(
    client: TestClient,
    runtime_config_enabled,
    authorized_target_type: str,
    authorized_target_id: str,
    requested_target_type: str,
    requested_target_id: str,
    expected_detail: str,
):
    """Provider says the credential is scoped to one target; body asks for another."""
    stub = _StubExchangeAuthorizer(
        target_type=authorized_target_type,
        target_id=authorized_target_id,
    )
    clear_authorizers()
    set_authorizer(stub)

    response = client.post(
        "/api/v1/auth/runtime-token-exchange",
        json={"target_type": requested_target_type, "target_id": requested_target_id},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == expected_detail


@pytest.mark.parametrize(
    ("payload", "expected_errors"),
    [
        ({"target_type": "log_stream"}, (("target_id", "missing"),)),
        ({"target_id": "opaque-target"}, (("target_type", "missing"),)),
        (
            {"target_type": None, "target_id": None},
            (("target_type", "string_type"), ("target_id", "string_type")),
        ),
        (
            {"target_type": "", "target_id": "opaque-target"},
            (("target_type", "string_too_short"),),
        ),
        (
            {"target_type": "log_stream", "target_id": 42},
            (("target_id", "string_type"),),
        ),
    ],
)
def test_exchange_endpoint_rejects_invalid_target_before_authorization(
    client: TestClient,
    payload: dict[str, object],
    expected_errors: tuple[tuple[str, str], ...],
):
    stub = _StubExchangeAuthorizer()
    clear_authorizers()
    set_authorizer(stub)

    response = client.post(
        "/api/v1/auth/runtime-token-exchange",
        json=payload,
    )
    assert response.status_code == 422
    response_body = response.json()
    assert response_body["detail"] == "Invalid runtime token target context."
    assert [(error["field"], error["code"]) for error in response_body["errors"]] == list(
        expected_errors
    )
    assert all("value" not in error for error in response_body["errors"])
    assert stub.calls == []


def test_exchange_endpoint_rejects_non_object_body_before_authorization(client: TestClient):
    stub = _StubExchangeAuthorizer()
    clear_authorizers()
    set_authorizer(stub)

    response = client.post("/api/v1/auth/runtime-token-exchange", json=[])

    assert response.status_code == 422
    assert response.json()["detail"] == "Runtime token exchange body must be a valid JSON object."
    assert stub.calls == []


def test_exchange_endpoint_rejects_non_json_before_authorization(client: TestClient):
    stub = _StubExchangeAuthorizer()
    clear_authorizers()
    set_authorizer(stub)

    response = client.post(
        "/api/v1/auth/runtime-token-exchange",
        content="not-json",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Runtime token exchange body must be a valid JSON object."
    assert stub.calls == []


def test_exchange_endpoint_defers_unknown_fields_to_body_validation(client: TestClient):
    stub = _StubExchangeAuthorizer()
    clear_authorizers()
    set_authorizer(stub)

    response = client.post(
        "/api/v1/auth/runtime-token-exchange",
        json={"target_type": "log_stream", "target_id": "ls-1", "bogus": 1},
    )

    assert response.status_code == 422
    response_body = response.json()
    assert [(error["field"], error["code"]) for error in response_body["errors"]] == [
