"""Unit tests for agent_control.controls API wrappers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

import agent_control
from agent_control_models import TemplateControlInput


@pytest.mark.asyncio
async def test_list_controls_passes_template_backed_filter() -> None:
    # Given: an SDK client stub and a template-backed list filter
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"controls": [], "pagination": {}})
    client = SimpleNamespace(http_client=SimpleNamespace(get=AsyncMock(return_value=response)))

    # When: listing controls through the SDK wrapper
    await agent_control.controls.list_controls(client, template_backed=True)

    # Then: the filter is forwarded to the API request
    client.http_client.get.assert_awaited_once_with(
        "/api/v1/controls",
        params={"limit": 20, "template_backed": True},
    )


@pytest.mark.asyncio
async def test_list_controls_passes_cloned_filter() -> None:
    # Given: an SDK client stub and a cloned list filter
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"controls": [], "pagination": {}})
    client = SimpleNamespace(http_client=SimpleNamespace(get=AsyncMock(return_value=response)))

    # When: listing controls through the SDK wrapper
    await agent_control.controls.list_controls(client, cloned=False)

    # Then: the filter is forwarded to the API request
    client.http_client.get.assert_awaited_once_with(
        "/api/v1/controls",
        params={"limit": 20, "cloned": False},
    )


@pytest.mark.asyncio
async def test_list_controls_passes_attachment_filters() -> None:
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"controls": [], "pagination": {}})
    client = SimpleNamespace(http_client=SimpleNamespace(get=AsyncMock(return_value=response)))

    await agent_control.controls.list_controls(
        client,
        include_attachments=True,
        attachment_target_type="log_stream",
        attachment_target_id="ls-prod",
    )

    client.http_client.get.assert_awaited_once_with(
        "/api/v1/controls",
        params={
            "limit": 20,
            "include_attachments": True,
            "attachment_target_type": "log_stream",
            "attachment_target_id": "ls-prod",
        },
    )


@pytest.mark.asyncio
async def test_create_control_accepts_template_control_input() -> None:
    # Given: an SDK client stub and template-backed control input
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"control_id": 123})
    client = SimpleNamespace(http_client=SimpleNamespace(put=AsyncMock(return_value=response)))
    template_input = TemplateControlInput.model_validate(
        {
            "template": {
                "parameters": {
                    "pattern": {
                        "type": "regex_re2",
                        "label": "Pattern",
                    }
                },
                "definition_template": {
                    "execution": "server",
                    "scope": {"step_types": ["llm"], "stages": ["pre"]},
                    "condition": {
                        "selector": {"path": "input"},
                        "evaluator": {
                            "name": "regex",
                            "config": {"pattern": {"$param": "pattern"}},
                        },
                    },
                    "action": {"decision": "deny"},
                },
            },
            "template_values": {"pattern": "hello"},
        }
    )

    # When: creating a control through the SDK wrapper
    await agent_control.controls.create_control(client, "templated", template_input)

    # Then: the template values are serialized into the request body
    client.http_client.put.assert_awaited_once()
    _, kwargs = client.http_client.put.await_args
    assert kwargs["json"]["data"]["template_values"]["pattern"] == "hello"


@pytest.mark.asyncio
async def test_clone_and_bind_control_calls_clone_endpoint() -> None:
    # Given: an SDK client stub for clone-and-bind
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(
        return_value={
            "id": 456,
            "name": "clone-name",
            "cloned_from_control_id": 123,
            "binding_id": 789,
        }
    )
    client = SimpleNamespace(http_client=SimpleNamespace(post=AsyncMock(return_value=response)))

    # When: cloning and binding through the SDK wrapper
    result = await agent_control.controls.clone_and_bind_control(
        client,
        123,
        target_type="log_stream",
        target_id="logstream-123",
        name="clone-name",
        enabled=False,
    )

    # Then: the SDK posts the expected payload
    assert result["id"] == 456
    client.http_client.post.assert_awaited_once_with(
        "/api/v1/controls/123/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-123",
                "enabled": False,
            },
            "name": "clone-name",
        },
    )


@pytest.mark.asyncio
async def test_top_level_list_controls_passes_cloned_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stub_client = object()

    @asynccontextmanager
    async def fake_ad_hoc_client(**kwargs: Any) -> AsyncGenerator[object, None]:
        captured["client_kwargs"] = kwargs
        yield stub_client

    async def fake_list_controls(client: object, **kwargs: Any) -> dict[str, Any]:
        captured["client"] = client
        captured["list_kwargs"] = kwargs
        return {"controls": [], "pagination": {}}

    monkeypatch.setattr(agent_control, "_ad_hoc_client", fake_ad_hoc_client)
    monkeypatch.setattr(agent_control.controls, "list_controls", fake_list_controls)

    result = await agent_control.list_controls(
        cloned=False,
        include_attachments=True,
        attachment_target_type="log_stream",
        attachment_target_id="ls-prod",
        server_url="http://server",
    )

    assert result["controls"] == []
    assert captured["client"] is stub_client
    assert captured["client_kwargs"]["server_url"] == "http://server"
    assert captured["list_kwargs"]["cloned"] is False
    assert captured["list_kwargs"]["include_attachments"] is True
    assert captured["list_kwargs"]["attachment_target_type"] == "log_stream"
    assert captured["list_kwargs"]["attachment_target_id"] == "ls-prod"


@pytest.mark.asyncio
async def test_top_level_clone_and_bind_control_uses_ad_hoc_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stub_client = object()

    @asynccontextmanager
    async def fake_ad_hoc_client(**kwargs: Any) -> AsyncGenerator[object, None]:
        captured["client_kwargs"] = kwargs
        yield stub_client

    async def fake_clone_and_bind_control(
        client: object,
        control_id: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured["client"] = client
        captured["control_id"] = control_id
        captured["clone_kwargs"] = kwargs
        return {"id": 456, "binding_id": 789}

    monkeypatch.setattr(agent_control, "_ad_hoc_client", fake_ad_hoc_client)
    monkeypatch.setattr(
        agent_control.controls,
        "clone_and_bind_control",
        fake_clone_and_bind_control,
    )

    result = await agent_control.clone_and_bind_control(
        123,
        target_type="log_stream",
        target_id="logstream-123",
        name="clone-name",
        enabled=False,
        server_url="http://server",
    )

    assert result["binding_id"] == 789
    assert captured["client"] is stub_client
    assert captured["client_kwargs"]["server_url"] == "http://server"
    assert captured["control_id"] == 123
    assert captured["clone_kwargs"] == {
        "target_type": "log_stream",
        "target_id": "logstream-123",
        "name": "clone-name",
        "enabled": False,
    }


@pytest.mark.asyncio
async def test_list_control_versions_forwards_cursor_and_limit() -> None:
    # Given: an SDK client stub and version-history pagination params
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"versions": [], "pagination": {}})
    client = SimpleNamespace(http_client=SimpleNamespace(get=AsyncMock(return_value=response)))

    # When: listing control versions through the SDK wrapper
    await agent_control.controls.list_control_versions(client, control_id=123, cursor=7, limit=5)
