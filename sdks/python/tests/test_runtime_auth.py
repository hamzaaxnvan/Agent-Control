"""Tests for Agent Control SDK runtime auth helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from agent_control.runtime_auth import (
    RuntimeToken,
    RuntimeTokenCache,
    normalize_runtime_auth_mode,
    parse_runtime_token_exchange_response,
)


def _runtime_token(
    *,
    token: str = "token",
    server_url: str = "https://server-a.test",
    target_type: str = "log_stream",
    target_id: str = "ls-1",
    expires_at: datetime | None = None,
) -> RuntimeToken:
    return RuntimeToken(
        token=token,
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=5),
        server_url=server_url,
        target_type=target_type,
        target_id=target_id,
        scopes=("runtime.use",),
    )


def test_runtime_token_cache_is_keyed_by_server_and_target() -> None:
    cache = RuntimeTokenCache()
    token = _runtime_token()

    cache.set(token)

    assert (
        cache.get("https://server-a.test", "log_stream", "ls-1", refresh_margin_seconds=0) == token
    )
    assert (
        cache.get("https://server-b.test", "log_stream", "ls-1", refresh_margin_seconds=0) is None
    )
    assert (
        cache.get("https://server-a.test", "log_stream", "ls-2", refresh_margin_seconds=0) is None
    )


def test_runtime_token_cache_is_keyed_by_client_identity() -> None:
    cache = RuntimeTokenCache()
    token = _runtime_token()

    cache.set(token, cache_identity="client-a")

    assert (
        cache.get(
            "https://server-a.test",
            "log_stream",
            "ls-1",
            cache_identity="client-a",
            refresh_margin_seconds=0,
        )
        == token
    )
    assert (
        cache.get(
            "https://server-a.test",
            "log_stream",
            "ls-1",
            cache_identity="client-b",
            refresh_margin_seconds=0,
        )
        is None
    )

    cache.mark_jwt_unavailable(
        server_url="https://server-a.test",
        target_type="log_stream",
        target_id="ls-1",
        cache_identity="client-b",
    )

    assert not cache.is_jwt_unavailable(
        "https://server-a.test",
        "log_stream",
        "ls-1",
        cache_identity="client-a",
    )
    assert cache.is_jwt_unavailable(
        "https://server-a.test",
        "log_stream",
        "ls-1",
        cache_identity="client-b",
    )


def test_runtime_token_repr_redacts_jwt() -> None:
    token = _runtime_token(token="raw-jwt-value")

    assert "raw-jwt-value" not in repr(token)


def test_runtime_token_cache_drops_stale_tokens() -> None:
    cache = RuntimeTokenCache()
    cache.set(_runtime_token(expires_at=datetime.now(UTC) + timedelta(seconds=5)))

    assert (
        cache.get("https://server-a.test", "log_stream", "ls-1", refresh_margin_seconds=30) is None
    )
    assert (
        cache.get("https://server-a.test", "log_stream", "ls-1", refresh_margin_seconds=0) is None
    )


def test_runtime_token_cache_tracks_jwt_unavailable_by_server_and_target() -> None:
    cache = RuntimeTokenCache()

    cache.mark_jwt_unavailable(
        server_url="https://server-a.test",
        target_type="log_stream",
        target_id="ls-1",
    )

    assert cache.is_jwt_unavailable("https://server-a.test", "log_stream", "ls-1")
    assert not cache.is_jwt_unavailable("https://server-b.test", "log_stream", "ls-1")

    cache.set(_runtime_token())

    assert not cache.is_jwt_unavailable("https://server-a.test", "log_stream", "ls-1")


def test_runtime_token_cache_target_unavailable_marker_expires() -> None:
    cache = RuntimeTokenCache()

    cache.mark_jwt_unavailable(
        server_url="https://server-a.test",
        target_type="log_stream",
        target_id="ls-1",
        ttl_seconds=0,
    )

    assert not cache.is_jwt_unavailable("https://server-a.test", "log_stream", "ls-1")

