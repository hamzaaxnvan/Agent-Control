"""Tests for API key authentication."""

import uuid
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from agent_control_server import __version__ as server_version
from agent_control_server.auth_framework import Operation, Principal, set_authorizer
from agent_control_server.config import auth_settings

from .utils import VALID_CONTROL_PAYLOAD


class _RecordingAuthorizer:
    """Test authorizer that records the operation requested by a route."""

    def __init__(self) -> None:
        self.calls: list[tuple[Operation, dict[str, Any] | None]] = []

    async def authorize(
        self,
        request: Request,
        operation: Operation,
        context: dict[str, Any] | None = None,
    ) -> Principal:
        del request
        self.calls.append((operation, context))
        return Principal(namespace_key="default")


class TestHealthEndpoint:
    """Health endpoint should always be accessible without authentication."""

    def test_health_without_auth(self, unauthenticated_client: TestClient) -> None:
        """Given no API key, when requesting health, then returns 200 with healthy status."""
        # When:
        response = unauthenticated_client.get("/health")

        # Then:
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert response.headers["X-Agent-Control-Server-Version"] == server_version

    def test_health_with_auth(self, client: TestClient) -> None:
        """Given valid API key, when requesting health, then returns 200."""
        # When:
        response = client.get("/health")

        # Then:
        assert response.status_code == 200


class TestProtectedEndpoints:
    """Protected endpoints require valid API key."""

    def test_missing_api_key_returns_401(self, unauthenticated_client: TestClient) -> None:
        """Given no API key, when requesting protected endpoint, then returns 401."""
        # When:
        response = unauthenticated_client.get("/api/v1/agents/00000000-0000-0000-0000-000000000000")

        # Then:
        assert response.status_code == 401
        assert "Missing credentials" in response.json()["detail"]
        assert response.headers["X-Agent-Control-Server-Version"] == server_version

    def test_invalid_api_key_returns_401(self, app: object) -> None:
        """Given invalid API key, when requesting protected endpoint, then returns 401."""
        # Given:
        client = TestClient(
            app,
            raise_server_exceptions=True,
            headers={"X-API-Key": "wrong-key"},
        )

        # When:
        response = client.get("/api/v1/agents/00000000-0000-0000-0000-000000000000")

        # Then:
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_valid_api_key_succeeds(self, non_admin_client: TestClient) -> None:
        """Given valid API key, when requesting protected endpoint, then request is accepted."""
        # When:
        response = non_admin_client.get("/api/v1/agents/00000000-0000-0000-0000-000000000000")

        # Then: (404 expected for non-existent resource, but NOT 401/403)
        assert response.status_code == 404

    def test_admin_key_works_on_protected_endpoints(self, admin_client: TestClient) -> None:
        """Given admin API key, when requesting protected endpoint, then request is accepted."""
        # When:
        response = admin_client.get("/api/v1/agents/00000000-0000-0000-0000-000000000000")

        # Then: (404 expected for non-existent resource, but NOT 401/403)
        assert response.status_code == 404


class TestEvaluatorsEndpoint:
    """Evaluators endpoint requires valid API key (regular or admin)."""

    def test_regular_key_works_on_evaluators(self, non_admin_client: TestClient) -> None:
        """Given regular API key, when listing evaluators, then returns 200."""
        # When:
        response = non_admin_client.get("/api/v1/evaluators")

        # Then:
        assert response.status_code == 200

    def test_admin_key_works_on_evaluators(self, admin_client: TestClient) -> None:
        """Given admin API key, when listing evaluators, then returns 200."""
        # When:
        response = admin_client.get("/api/v1/evaluators")

        # Then:
        assert response.status_code == 200

    def test_missing_key_returns_401_on_evaluators(
        self, unauthenticated_client: TestClient
    ) -> None:
        """Given no API key, when listing evaluators, then returns 401."""
        # When:
        response = unauthenticated_client.get("/api/v1/evaluators")

        # Then:
        assert response.status_code == 401

    def test_evaluators_use_auth_framework_provider(self, app: object) -> None:
        """Given a custom authorizer, when listing evaluators, then route uses it."""
        # Given:
        authorizer = _RecordingAuthorizer()
        set_authorizer(authorizer)
        client = TestClient(app, raise_server_exceptions=True)

