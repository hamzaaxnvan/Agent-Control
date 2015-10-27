"""HTTP-level coverage for the ``/control-bindings`` endpoints."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from agent_control_models.errors import ErrorCode, ErrorReason
from agent_control_server.auth_framework import Operation, Principal, set_authorizer
from agent_control_server.auth_framework.providers import (
    HeaderAuthProvider,
    HttpUpstreamAuthProvider,
)
from agent_control_server.auth_framework.providers.http_upstream import HttpUpstreamConfig
from agent_control_server.errors import APIError, ForbiddenError, NotFoundError
from agent_control_server.models import DEFAULT_NAMESPACE_KEY
from fastapi.testclient import TestClient
from httpx import Response

from .utils import VALID_CONTROL_PAYLOAD

_BINDINGS_URL = "/api/v1/control-bindings"


def _create_control(client: TestClient, name: str | None = None) -> int:
    payload = {
        "name": name or f"control-{uuid.uuid4().hex[:12]}",
        "data": VALID_CONTROL_PAYLOAD,
    }
    resp = client.put("/api/v1/controls", json=payload)
    assert resp.status_code == 200, resp.text
    return int(resp.json()["control_id"])


def _create_binding(
    client: TestClient,
    *,
    control_id: int,
    target_type: str = "env",
    target_id: str = "prod",
    enabled: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "target_type": target_type,
        "target_id": target_id,
        "control_id": control_id,
        "enabled": enabled,
    }
    resp = client.put(_BINDINGS_URL, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_create_binding_returns_id(client: TestClient) -> None:
    control_id = _create_control(client)
    body = _create_binding(client, control_id=control_id)
    assert isinstance(body["binding_id"], int)


def test_create_binding_with_unknown_control_returns_404(
    client: TestClient,
) -> None:
    resp = client.put(
        _BINDINGS_URL,
        json={
            "target_type": "env",
            "target_id": "prod",
            "control_id": 999_999,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "CONTROL_NOT_FOUND"


def test_create_duplicate_binding_returns_409(client: TestClient) -> None:
    control_id = _create_control(client)
    _create_binding(client, control_id=control_id)
    resp = client.put(
        _BINDINGS_URL,
        json={
            "target_type": "env",
            "target_id": "prod",
            "control_id": control_id,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONTROL_BINDING_CONFLICT"


def test_get_binding_returns_full_payload(client: TestClient) -> None:
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]

    resp = client.get(f"{_BINDINGS_URL}/{binding_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == binding_id
    assert body["control_id"] == control_id
    assert body["target_type"] == "env"
    assert body["target_id"] == "prod"
    assert body["enabled"] is True
    assert body["namespace_key"] == "default"


def test_get_unknown_binding_returns_404(client: TestClient) -> None:
    resp = client.get(f"{_BINDINGS_URL}/999999")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "CONTROL_BINDING_NOT_FOUND"


def test_binding_id_routes_authorize_the_stored_target(client: TestClient) -> None:
    # Given a binding whose opaque target is stored only in the database.
    control_id = _create_control(client)
    binding_id = _create_binding(
        client,
        control_id=control_id,
        target_type="custom_target",
        target_id="target-42",
    )["binding_id"]
    calls: list[tuple[str, Operation, dict[str, Any] | None]] = []

    class RecordingAuthorizer:
        binding_target_authorization = True

        async def resolve_identity(self, request: Any, operation: Operation) -> Principal:
            del request
            calls.append(("identity", operation, None))
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY, is_admin=True)

        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            del request
            calls.append(("authorize", operation, context))
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY, is_admin=True)

    set_authorizer(RecordingAuthorizer())

    # When each by-ID route is called without target data in the request.
    get_resp = client.get(f"{_BINDINGS_URL}/{binding_id}")
    patch_resp = client.patch(f"{_BINDINGS_URL}/{binding_id}", json={"enabled": False})
    delete_resp = client.delete(f"{_BINDINGS_URL}/{binding_id}")

    # Then every authorization call receives the target stored on the binding.
    assert get_resp.status_code == 200, get_resp.text
    assert patch_resp.status_code == 200, patch_resp.text
    assert delete_resp.status_code == 200, delete_resp.text
    target_context = {"target_type": "custom_target", "target_id": "target-42"}
    assert calls == [
        ("identity", Operation.CONTROL_BINDINGS_READ, None),
        ("authorize", Operation.CONTROL_BINDINGS_READ, target_context),
        ("identity", Operation.CONTROL_BINDINGS_WRITE, None),
        ("authorize", Operation.CONTROL_BINDINGS_WRITE, target_context),
        ("identity", Operation.CONTROL_BINDINGS_WRITE, None),
        ("authorize", Operation.CONTROL_BINDINGS_WRITE, target_context),
    ]


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
@pytest.mark.parametrize("exists", [True, False])
@pytest.mark.parametrize(
    ("api_key", "expected_error_code"),
    [(None, "AUTH_MISSING_KEY"), ("wrong-key", "AUTH_INVALID_KEY")],
)
def test_binding_id_routes_preserve_authentication_errors(
    method: str,
    exists: bool,
    api_key: str | None,
    expected_error_code: str,
    client: TestClient,
    app: object,
) -> None:
    # Given: a caller with no valid credential and an existing or missing ID.
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]
    headers = {} if api_key is None else {"X-API-Key": api_key}
    unauthorized_client = TestClient(app, raise_server_exceptions=True, headers=headers)

    # When: the caller accesses the binding by ID.
    url = f"{_BINDINGS_URL}/{binding_id if exists else 999_999}"
    if method == "get":
        response = unauthorized_client.get(url)
    elif method == "patch":
        response = unauthorized_client.patch(url, json={"enabled": False})
    else:
        response = unauthorized_client.delete(url)

    # Then: the route preserves the normal 401 challenge.
    assert response.status_code == 401
    assert response.json()["error_code"] == expected_error_code
    assert response.headers["WWW-Authenticate"] == "ApiKey"


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_binding_id_write_checks_local_access_before_lookup(
    method: str, non_admin_client: TestClient
) -> None:
    # Given: a valid non-admin key and a missing binding ID.
    url = f"{_BINDINGS_URL}/999999"

    # When: the caller attempts an ID-based write.
    if method == "patch":
        response = non_admin_client.patch(url, json={"enabled": False})
    else:
        response = non_admin_client.delete(url)

    # Then: the operation-wide access check preserves the normal 403.
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_binding_id_lookup_is_scoped_before_target_authorization(
    method: str, client: TestClient
) -> None:
    class NamespaceAuthorizer:
        binding_target_authorization = True
        namespace_key = "other-namespace"

        def __init__(self) -> None:
            self.target_calls = 0

        async def resolve_identity(self, request: Any, operation: Operation) -> Principal:
            del request, operation
            return Principal(namespace_key=self.namespace_key, is_admin=True)

        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            del request, operation, context
            self.target_calls += 1
            return Principal(namespace_key=self.namespace_key, is_admin=True)

    # Given: a binding in another namespace and an identity in the default namespace.
    authorizer = NamespaceAuthorizer()
    set_authorizer(authorizer)
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]
    authorizer.namespace_key = DEFAULT_NAMESPACE_KEY
    authorizer.target_calls = 0

    # When: the caller tries the foreign ID and a missing ID.
    def request_id(requested_id: int) -> Response:
        url = f"{_BINDINGS_URL}/{requested_id}"
        if method == "get":
            return client.get(url)
        if method == "patch":
            return client.patch(url, json={"enabled": False})
        return client.delete(url)

    foreign = request_id(binding_id)
    missing = request_id(999_999)

    # Then: neither ID reaches target authorization or mutates the binding.
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error_code"] == missing.json()["error_code"] == (
        "CONTROL_BINDING_NOT_FOUND"
    )
    assert authorizer.target_calls == 0
    authorizer.namespace_key = "other-namespace"
    stored = client.get(f"{_BINDINGS_URL}/{binding_id}")
    assert stored.status_code == 200
    assert stored.json()["enabled"] is True


def test_binding_id_identity_failure_does_not_depend_on_id(
    client: TestClient,
) -> None:
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]

    class UnavailableAuthorizer:
        binding_target_authorization = True

        async def resolve_identity(self, request: Any, operation: Operation) -> Principal:
            del request, operation
            raise APIError(
                status_code=503,
                error_code=ErrorCode.AUTH_MISCONFIGURED,
                reason=ErrorReason.SERVICE_UNAVAILABLE,
                detail="Authorization service unavailable.",
            )

        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            raise AssertionError("Target authorization must not run after identity failure")

    # Given: the identity service is unavailable before any binding lookup.
    set_authorizer(UnavailableAuthorizer())

    # When: the caller requests an existing and a missing ID.
    existing = client.get(f"{_BINDINGS_URL}/{binding_id}")
    missing = client.get(f"{_BINDINGS_URL}/999999")

    # Then: both fail with the same upstream error.
    assert existing.status_code == missing.status_code == 503
    assert existing.json()["error_code"] == missing.json()["error_code"] == "AUTH_MISCONFIGURED"


@pytest.mark.parametrize("denial", ["forbidden", "not_found"])
def test_binding_id_target_denial_looks_like_missing_binding(
    denial: str, client: TestClient
) -> None:
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]

    class DenyingAuthorizer:
        binding_target_authorization = True

        async def resolve_identity(self, request: Any, operation: Operation) -> Principal:
            del request, operation
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY)

        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            del request, operation, context
            if denial == "forbidden":
                raise ForbiddenError(
                    error_code=ErrorCode.AUTH_INSUFFICIENT_PRIVILEGES,
                    detail="Target access denied.",
                )
            raise NotFoundError(
                error_code=ErrorCode.AUTH_INVALID_KEY,
                detail="Target not found.",
                resource="Target",
            )

    # Given: an identity in the binding's namespace without target access.
    set_authorizer(DenyingAuthorizer())

    # When: the caller requests the denied binding and a missing ID.
    denied = client.get(f"{_BINDINGS_URL}/{binding_id}")
    missing = client.get(f"{_BINDINGS_URL}/999999")

    # Then: both use the binding-not-found response contract.
    assert denied.status_code == missing.status_code == 404
    assert denied.json()["error_code"] == missing.json()["error_code"] == (
        "CONTROL_BINDING_NOT_FOUND"
    )


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_binding_id_rejects_namespace_changed_by_target_authorization(
    method: str, client: TestClient
) -> None:
    # Given: identity resolves to the binding namespace, but target auth changes it.
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]

    class MismatchedNamespaceAuthorizer:
        binding_target_authorization = True
        authorization_namespace = "other-namespace"

        async def resolve_identity(self, request: Any, operation: Operation) -> Principal:
            del request, operation
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY)

        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            del request, operation, context
            return Principal(namespace_key=self.authorization_namespace)

    authorizer = MismatchedNamespaceAuthorizer()
    set_authorizer(authorizer)

    # When: the caller reads or mutates the binding by ID.
    url = f"{_BINDINGS_URL}/{binding_id}"
    if method == "get":
        response = client.get(url)
    elif method == "patch":
        response = client.patch(url, json={"enabled": False})
    else:
        response = client.delete(url)

    # Then: it looks missing, and PATCH/DELETE leave the row untouched.
    missing = client.get(f"{_BINDINGS_URL}/999999")
    assert response.status_code == missing.status_code == 404
    assert response.json()["error_code"] == missing.json()["error_code"] == (
        "CONTROL_BINDING_NOT_FOUND"
    )

    authorizer.authorization_namespace = DEFAULT_NAMESPACE_KEY
    stored = client.get(url)
    assert stored.status_code == 200, stored.text
    assert stored.json()["enabled"] is True


def test_binding_id_legacy_authorizer_preserves_namespace_wide_check(client: TestClient) -> None:
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]
    contexts: list[dict[str, Any] | None] = []

    class LegacyAuthorizer:
        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            del request, operation
            contexts.append(context)
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY)

    # Given: a provider that implements the original authorize-only contract.
    set_authorizer(LegacyAuthorizer())

    # When: an ID-based binding read succeeds.
    response = client.get(f"{_BINDINGS_URL}/{binding_id}")

    # Then: the legacy provider receives the same single targetless check as before.
    assert response.status_code == 200
    assert contexts == [None]


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("get", Operation.CONTROL_BINDINGS_READ),
        ("patch", Operation.CONTROL_BINDINGS_WRITE),
        ("delete", Operation.CONTROL_BINDINGS_WRITE),
    ],
)
@pytest.mark.parametrize(
    ("namespace_key", "expected_status"),
    [(DEFAULT_NAMESPACE_KEY, 200), ("other-namespace", 404)],
)
def test_binding_id_non_orbit_http_upstream_preserves_targetless_check(
    method: str,
    operation: Operation,
    namespace_key: str,
    expected_status: int,
    client: TestClient,
) -> None:
    control_id = _create_control(client)
    binding_id = _create_binding(client, control_id=control_id)["binding_id"]
    upstream_requests: list[httpx.Request] = []

    def upstream_auth(request: httpx.Request) -> Response:
        upstream_requests.append(request)
        if "context" in json.loads(request.content):
            # This upstream accepted the old namespace-wide contract only.
            return Response(400, json={"detail": "Unexpected target context"})
        return Response(200, json={"namespace_key": namespace_key})

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_auth))
    set_authorizer(
        HttpUpstreamAuthProvider(
            HttpUpstreamConfig(url="https://custom.example/check"),
            client=upstream_client,
        )
    )

    url = f"{_BINDINGS_URL}/{binding_id}"
    if method == "get":
        response = client.get(url)
    elif method == "patch":
        response = client.patch(url, json={"enabled": False})
    else:
        response = client.delete(url)

    assert response.status_code == expected_status, response.text
    assert len(upstream_requests) == 1
    assert str(upstream_requests[0].url) == "https://custom.example/check"
    assert upstream_requests[0].method == "POST"
    assert upstream_requests[0].headers["x-api-key"] == client.headers["x-api-key"]
    assert json.loads(upstream_requests[0].content) == {"operation": operation.value}
    if expected_status == 404:
        assert response.json()["error_code"] == "CONTROL_BINDING_NOT_FOUND"
    elif method == "get":
        assert response.json()["namespace_key"] == DEFAULT_NAMESPACE_KEY
    else:
        assert response.json()["success"] is True

    set_authorizer(HeaderAuthProvider())
    stored = client.get(url)
    if method == "delete" and expected_status == 200:
        assert stored.status_code == 404
    else:
        assert stored.status_code == 200
        assert stored.json()["enabled"] is (method != "patch" or expected_status != 200)


def test_binding_id_orbit_http_upstream_authorizes_stored_target(client: TestClient) -> None:
    # Given: Orbit requires target context for management authorization.
    control_id = _create_control(client)
    target_id = str(uuid.uuid4())
