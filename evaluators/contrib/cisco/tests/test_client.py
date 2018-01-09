from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from agent_control_evaluator_cisco.ai_defense.client import (
    AIDefenseClient,
    build_endpoint,
)


@pytest.mark.asyncio
async def test_chat_inspect_happy_path_builds_headers_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __init__(self, data: dict[str, Any]):
            self._data = data

        def raise_for_status(self) -> None:  # no-op
            return None

        def json(self) -> dict[str, Any]:
            return self._data

    class FakeAsyncClient:
        def __init__(self, *_, **kwargs: Any):
            captured["timeout"] = kwargs.get("timeout")
            self.is_closed = False

        async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse({"ok": True, "is_safe": True})

        async def aclose(self) -> None:
            self.is_closed = True

    # Patch the constructor used by the module
    from agent_control_evaluator_cisco.ai_defense import client as client_mod

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", FakeAsyncClient, raising=True)

    c = AIDefenseClient(
        api_key="k",
        endpoint_url="https://example.test/api/v1/inspect/chat",
        timeout_s=7.5,
    )

    data = await c.chat_inspect(
        messages=[{"role": "user", "content": "hello"}],
        metadata={"trace_id": "t1"},
        inspect_config={"mode": "strict"},
        headers={"X-Extra": "1"},
    )

    assert data["ok"] is True
    assert captured["url"] == "https://example.test/api/v1/inspect/chat"
    assert captured["timeout"] == 7.5
    # Headers
    assert captured["headers"]["X-Cisco-AI-Defense-API-Key"] == "k"
    assert captured["headers"]["X-Extra"] == "1"
    assert captured["headers"]["Content-Type"] == "application/json"
    # Payload
    assert captured["json"]["messages"][0]["content"] == "hello"
    assert captured["json"]["metadata"] == {"trace_id": "t1"}
    assert captured["json"]["config"] == {"mode": "strict"}
    assert "api_key='k'" not in repr(c)


@pytest.mark.asyncio
async def test_chat_inspect_non_dict_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> Any:  # not a dict
            return [1, 2, 3]

    class FakeAsyncClient:
        def __init__(self, *_, **__):
            self.is_closed = False

        async def post(self, *_: Any, **__: Any):
            return FakeResponse()

        async def aclose(self) -> None:
            self.is_closed = True

    from agent_control_evaluator_cisco.ai_defense import client as client_mod

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", FakeAsyncClient, raising=True)

    c = AIDefenseClient(api_key="k", endpoint_url="https://x/api/v1/inspect/chat", timeout_s=5)

    with pytest.raises(RuntimeError, match="not a JSON object"):
        await c.chat_inspect(messages=[{"role": "user", "content": "x"}])


@pytest.mark.asyncio
async def test_chat_inspect_http_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHTTPError(Exception):
        pass

    class FakeResponse:
        def raise_for_status(self) -> None:
            raise FakeHTTPError("bad status")

