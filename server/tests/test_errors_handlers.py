"""Tests for error handlers."""

import json
import logging

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from starlette.requests import Request

from agent_control_server.errors import (
    InternalError,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


@pytest.mark.asyncio
async def test_http_exception_handler_sets_www_authenticate() -> None:
    # Given: a 401 HTTPException
    request = Request({"type": "http", "method": "GET", "path": "/protected", "headers": []})
    exc = HTTPException(status_code=401, detail="missing api key")

    # When: handling the HTTPException
    response = await http_exception_handler(request, exc)

    # Then: response is RFC 7807 with WWW-Authenticate header
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "ApiKey"
    body = json.loads(response.body.decode("utf-8"))
    assert body["error_code"] == "AUTH_INVALID_KEY"


@pytest.mark.asyncio
async def test_generic_exception_handler_never_exposes_exception_details(monkeypatch) -> None:
    # Given: local debug flags are enabled
    monkeypatch.setenv("AGENT_CONTROL_EXPOSE_ERRORS", "true")
    request = Request({"type": "http", "method": "GET", "path": "/boom", "headers": []})

    # When: handling an unexpected exception
    response = await generic_exception_handler(request, ValueError("boom"))

    # Then: response remains public-safe and does not include internals
    assert response.status_code == 500
    body = json.loads(response.body.decode("utf-8"))
    assert body["detail"] == "An unexpected error occurred. Please try again or contact support."
    assert "ValueError" not in body["detail"]
    assert body["metadata"]["request_id"]


@pytest.mark.asyncio
async def test_generic_exception_handler_logs_full_traceback(
    caplog: pytest.LogCaptureFixture,
