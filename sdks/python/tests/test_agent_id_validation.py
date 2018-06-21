"""SDK agent name validation behavior tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_control import agents, policies


class DummyResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ok": True}


@pytest.mark.asyncio
async def test_get_agent_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.get = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.get_agent(client, "short")

    client.http_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_agent_policy_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.get = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.get_agent_policy(client, "short")

    client.http_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_agent_policies_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.get = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.get_agent_policies(client, "short")

    client.http_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_remove_agent_policy_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.delete = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.remove_agent_policy(client, "short")

    client.http_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_remove_all_agent_policies_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.delete = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.remove_all_agent_policies(client, "short")

    client.http_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_add_agent_policy_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.post = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.add_agent_policy(client, "short", policy_id=1)

    client.http_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_remove_agent_policy_association_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.delete = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.remove_agent_policy_association(client, "short", policy_id=1)

    client.http_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_add_agent_control_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.post = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.add_agent_control(client, "short", control_id=1)

    client.http_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_remove_agent_control_rejects_invalid_agent_name() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.delete = AsyncMock()

    with pytest.raises(ValueError, match="at least 10 characters"):
        await agents.remove_agent_control(client, "short", control_id=1)

    client.http_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_list_agents_normalizes_cursor() -> None:
    client = MagicMock()
    client.http_client = MagicMock()
    client.http_client.get = AsyncMock(return_value=DummyResponse())

    await agents.list_agents(client, cursor="Agent-Example_01", limit=5)

