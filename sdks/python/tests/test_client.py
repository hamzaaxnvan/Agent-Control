"""Unit tests for AgentControlClient configuration and version warnings."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

import agent_control
from agent_control.client import AgentControlClient, sdk_version
from agent_control.runtime_auth import RuntimeTokenCache


def test_client_uses_agent_control_url_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: AGENT_CONTROL_URL is set in the environment
    monkeypatch.setenv("AGENT_CONTROL_URL", "http://example.test:9000/")

    # When: constructing a client without an explicit base URL
    client = AgentControlClient()

    # Then: the client uses the environment-provided server URL
    assert client.base_url == "http://example.test:9000"


def test_explicit_base_url_overrides_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: AGENT_CONTROL_URL is set but an explicit base URL is also provided
    monkeypatch.setenv("AGENT_CONTROL_URL", "http://env.test:9000")

    # When: constructing the client with an explicit base URL
    client = AgentControlClient(base_url="http://explicit.test:8000/")

    # Then: the explicit base URL wins
    assert client.base_url == "http://explicit.test:8000"


def test_get_headers_include_sdk_metadata() -> None:
    # Given: a client configured with an API key
    client = AgentControlClient(api_key="test-key")

    # When: building request headers
    headers = client._get_headers()

    # Then: SDK metadata headers are included
    assert headers["X-Agent-Control-SDK"] == "python"
    assert headers["X-Agent-Control-SDK-Version"] == sdk_version
    assert "X-API-Key" not in headers


def test_client_rejects_negative_runtime_token_refresh_margin() -> None:
    with pytest.raises(ValueError, match="runtime_token_refresh_margin_seconds"):
        AgentControlClient(runtime_token_refresh_margin_seconds=-1)


@pytest.mark.asyncio
async def test_client_adds_api_key_auth_to_regular_requests() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async with AgentControlClient(
        base_url="https://agent-control.test",
        api_key="test-key",
        transport=transport,
    ) as client:
        response = await client.http_client.get("/api/v1/agents")

    assert response.status_code == 200
    assert seen_requests[0].headers["X-API-Key"] == "test-key"


@pytest.mark.asyncio
async def test_client_uses_configured_api_key_header_name() -> None:
    # Given: a client configured to send the API key on a custom header
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async with AgentControlClient(
        base_url="https://agent-control.test",
        api_key="test-key",
        api_key_header="X-Custom-API-Key",
        transport=transport,
    ) as client:
        # When: making a request
        response = await client.http_client.get("/api/v1/agents")

    # Then: the key is on the configured header and the default is absent
    assert response.status_code == 200
    assert seen_requests[0].headers["X-Custom-API-Key"] == "test-key"
    assert "X-API-Key" not in seen_requests[0].headers


@pytest.mark.asyncio
async def test_client_reads_api_key_header_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: AGENT_CONTROL_API_KEY_HEADER set in the environment
    monkeypatch.setenv("AGENT_CONTROL_API_KEY_HEADER", "X-Custom-API-Key")
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async with AgentControlClient(
        base_url="https://agent-control.test",
        api_key="test-key",
        transport=transport,
    ) as client:
        # When: no api_key_header is passed to the constructor
        response = await client.http_client.get("/api/v1/agents")

    # Then: the env-var value is used
    assert response.status_code == 200
    assert seen_requests[0].headers["X-Custom-API-Key"] == "test-key"


def test_client_exposes_default_api_key_header() -> None:
    # Given: a client with no explicit header override
    client = AgentControlClient(api_key="test-key")

    # Then: the property reports the documented default
    assert client.api_key_header == "X-API-Key"


@pytest.mark.asyncio
async def test_get_agent_convenience_forwards_api_key_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_client_kwargs: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured_client_kwargs.update(kwargs)

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    async def fake_get_agent(client: object, agent_name: str) -> dict[str, object]:
        return {"client": client, "agent_name": agent_name}

    monkeypatch.setattr(agent_control, "AgentControlClient", FakeClient)
    monkeypatch.setattr(agent_control.agents, "get_agent", fake_get_agent)

    result = await agent_control.get_agent(
        "agent-a",
        server_url="https://agent-control.test",
        api_key="test-key",
        api_key_header="X-Custom-API-Key",
    )

    assert result["agent_name"] == "agent-a"
    assert captured_client_kwargs == {
        "base_url": "https://agent-control.test",
        "api_key": "test-key",
        "api_key_header": "X-Custom-API-Key",
    }


@pytest.mark.asyncio
async def test_runtime_evaluation_exchanges_and_caches_bearer_token() -> None:
    exchange_calls = 0
    evaluation_authorization_headers: list[str | None] = []
    evaluation_api_key_headers: list[str | None] = []
    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal exchange_calls
        if request.url.path == "/api/v1/auth/runtime-token-exchange":
            exchange_calls += 1
            assert request.headers["X-API-Key"] == "test-key"
            return httpx.Response(
                200,
                json={
                    "token": "runtime-token",
                    "expires_at": expires_at,
                    "target_type": "log_stream",
                    "target_id": "ls-1",
                    "scopes": ["runtime.use"],
                },
            )

        evaluation_authorization_headers.append(request.headers.get("Authorization"))
        evaluation_api_key_headers.append(request.headers.get("X-API-Key"))
        return httpx.Response(200, json={"is_safe": True, "confidence": 1.0})

    transport = httpx.MockTransport(handler)

    async with AgentControlClient(
        base_url="https://agent-control.test",
        api_key="test-key",
        runtime_auth_mode="auto",
        transport=transport,
    ) as client:
        for _ in range(2):
            response = await client.post_runtime_evaluation(
                json={"target_type": "log_stream", "target_id": "ls-1"},
                target_type="log_stream",
                target_id="ls-1",
            )
            assert response.status_code == 200

    assert exchange_calls == 1
    assert evaluation_authorization_headers == ["Bearer runtime-token", "Bearer runtime-token"]
    assert evaluation_api_key_headers == [None, None]


@pytest.mark.asyncio
async def test_runtime_evaluation_single_flights_cold_cache_exchange() -> None:
    exchange_calls = 0
    evaluation_authorization_headers: list[str | None] = []
    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal exchange_calls
        if request.url.path == "/api/v1/auth/runtime-token-exchange":
            exchange_calls += 1
            await asyncio.sleep(0.01)
            return httpx.Response(
                200,
                json={
                    "token": "runtime-token",
                    "expires_at": expires_at,
                    "target_type": "log_stream",
                    "target_id": "ls-1",
                    "scopes": ["runtime.use"],
                },
            )

        evaluation_authorization_headers.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"is_safe": True, "confidence": 1.0})

    transport = httpx.MockTransport(handler)

    async with AgentControlClient(
        base_url="https://agent-control.test",
        api_key="test-key",
        runtime_auth_mode="jwt",
        transport=transport,
    ) as client:
        responses = await asyncio.gather(
            *(
                client.post_runtime_evaluation(
                    json={"target_type": "log_stream", "target_id": "ls-1"},
                    target_type="log_stream",
