"""Tests that init() surfaces server-side conflicts."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import agent_control
import httpx
import pytest


def _make_conflict_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://localhost:8000/api/v1/agents/initAgent")
    response = httpx.Response(409, request=request)
    return httpx.HTTPStatusError(
        "Client error '409 Conflict' for url 'http://localhost:8000/api/v1/agents/initAgent'",
        request=request,
        response=response,
    )
