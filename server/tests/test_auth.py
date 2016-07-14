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

        # When:
        response = client.get("/api/v1/evaluators")

        # Then:
        assert response.status_code == 200
        assert authorizer.calls == [(Operation.EVALUATORS_READ, None)]


class TestAuthDisabled:
    """When auth is disabled, all requests should succeed."""

    @pytest.fixture(autouse=True)
    def disable_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Disable auth for tests in this class."""
        monkeypatch.setattr(auth_settings, "api_key_enabled", False)

    def test_no_key_allowed_when_disabled(self, unauthenticated_client: TestClient) -> None:
        """Given auth disabled, when requesting without API key, then request succeeds."""
        # When:
        response = unauthenticated_client.get("/api/v1/agents/00000000-0000-0000-0000-000000000000")

        # Then: (404 for non-existent resource, but NOT 401)
        assert response.status_code == 404

    def test_evaluators_accessible_when_disabled(self, unauthenticated_client: TestClient) -> None:
        """Given auth disabled, when listing evaluators without API key, then returns 200."""
        # When:
        response = unauthenticated_client.get("/api/v1/evaluators")

        # Then:
        assert response.status_code == 200


_VALID_CONTROL_DATA = {
    "description": "Test Control",
    "enabled": True,
    "execution": "server",
    "scope": {"step_types": ["llm"], "stages": ["pre"]},
    "condition": {
        "selector": {"path": "input"},
        "evaluator": {
            "name": "regex",
            "config": {"pattern": "test", "flags": []},
        },
    },
    "action": {"decision": "deny"},
    "tags": ["test"],
}


class TestAdminWriteEndpointAuthorization:
    """Mutation endpoints require admin API keys."""

    @pytest.mark.parametrize(
        ("method", "path", "json_body"),
        [
            (
                "PUT",
                "/api/v1/controls",
                {"name": "control-authz-blocked", "data": _VALID_CONTROL_DATA},
            ),
            ("PUT", "/api/v1/controls/1/data", {"data": _VALID_CONTROL_DATA}),
            ("PATCH", "/api/v1/controls/1", {"enabled": False}),
            ("DELETE", "/api/v1/controls/1", None),
            ("PUT", "/api/v1/policies", {"name": "policy-authz-blocked"}),
            ("POST", "/api/v1/policies/1/controls/1", None),
            ("DELETE", "/api/v1/policies/1/controls/1", None),
            ("POST", "/api/v1/agents/agent-authz-test01/policies/1", None),
            ("POST", "/api/v1/agents/agent-authz-test01/policy/1", None),
            ("DELETE", "/api/v1/agents/agent-authz-test01/policies/1", None),
            ("DELETE", "/api/v1/agents/agent-authz-test01/policies", None),
            ("DELETE", "/api/v1/agents/agent-authz-test01/policy", None),
            ("POST", "/api/v1/agents/agent-authz-test01/controls/1", None),
            ("DELETE", "/api/v1/agents/agent-authz-test01/controls/1", None),
            (
                "PATCH",
                "/api/v1/agents/agent-authz-test01",
                {"remove_steps": [], "remove_evaluators": []},
            ),
        ],
    )
    def test_non_admin_key_denied_on_admin_only_mutations(
        self,
        non_admin_client: TestClient,
        method: str,
        path: str,
        json_body: dict[str, object] | None,
    ) -> None:
        response = non_admin_client.request(method, path, json=json_body)

        assert response.status_code == 403
        body = response.json()
        assert body["error_code"] == "AUTH_INSUFFICIENT_PRIVILEGES"

    def test_non_admin_key_can_init_agent_and_fetch_controls(
        self, non_admin_client: TestClient
    ) -> None:
        agent_name = f"runtime-agent-{uuid.uuid4().hex[:8]}"
        init_payload = {
            "agent": {
                "agent_name": agent_name,
                "agent_description": "Runtime agent",
                "agent_version": "1.0",
            },
            "steps": [
                {
                    "type": "tool",
                    "name": "tool_a",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            ],
            "evaluators": [],
        }

        init_response = non_admin_client.post("/api/v1/agents/initAgent", json=init_payload)
        assert init_response.status_code == 200

        controls_response = non_admin_client.get(f"/api/v1/agents/{agent_name}/controls")
        assert controls_response.status_code == 200
        assert controls_response.json()["controls"] == []

    def test_admin_key_allowed_on_representative_mutations(self, admin_client: TestClient) -> None:
        control_name = f"control-authz-{uuid.uuid4().hex[:8]}"
        control_response = admin_client.put(
            "/api/v1/controls",
            json={"name": control_name, "data": VALID_CONTROL_PAYLOAD},
        )
        assert control_response.status_code == 200
        control_id = control_response.json()["control_id"]

        policy_name = f"policy-authz-{uuid.uuid4().hex[:8]}"
        policy_response = admin_client.put("/api/v1/policies", json={"name": policy_name})
        assert policy_response.status_code == 200
        policy_id = policy_response.json()["policy_id"]

        add_control_response = admin_client.post(
            f"/api/v1/policies/{policy_id}/controls/{control_id}"
        )
