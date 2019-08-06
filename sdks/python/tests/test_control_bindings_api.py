"""Unit tests for agent_control.control_bindings API wrappers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import agent_control
import pytest


@pytest.mark.asyncio
async def test_upsert_control_binding_by_key_calls_endpoint() -> None:
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"binding_id": 123, "created": True, "enabled": True})
    client = SimpleNamespace(http_client=SimpleNamespace(put=AsyncMock(return_value=response)))
