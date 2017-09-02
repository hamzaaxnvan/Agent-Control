"""Unit tests for agent_control.agents API wrappers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

import agent_control


@pytest.mark.asyncio
async def test_list_agent_controls_typed_calls_controls_endpoint() -> None:
    # GIVEN: a successful HTTP response payload for controls.
    response_payload = {"controls": []}
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value=response_payload)
    client = SimpleNamespace(http_client=SimpleNamespace(get=AsyncMock(return_value=response)))
    agent_name = str(uuid4())

