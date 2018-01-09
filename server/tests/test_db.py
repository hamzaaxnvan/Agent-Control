"""Tests for server database engine configuration."""

import logging
from typing import cast

import pytest
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio.engine import AsyncEngine

from agent_control_server.config import AgentControlServerDatabaseConfig
from agent_control_server.db import (
    _build_async_engine_kwargs,
    _checked_out_connection_count,
    _instrument_connection_pool,
    async_engine,
)


class _PoolWithCheckedout:
    def __init__(self, value: int) -> None:
        self.value = value

    def checkedout(self) -> int:
        return self.value


class _PoolWithoutCheckedout:
    pass


class _SyncEngine:
    def __init__(self, pool: object) -> None:
        self.pool = pool


class _Engine:
    def __init__(self, pool: object) -> None:
        self.sync_engine = _SyncEngine(pool)


def _engine_with_pool(pool: object) -> AsyncEngine:
    return cast(AsyncEngine, _Engine(pool))


def _checked_out_connections_sample() -> float | None:
    return REGISTRY.get_sample_value(
        "agent_control_server_sqlalchemy_checked_out_connections",
        {"pool_name": "default"},
    )


def test_build_async_engine_kwargs_applies_postgres_pool_config() -> None:
    # Given: custom PostgreSQL connection pool and timeout settings
    config = AgentControlServerDatabaseConfig(
        pool_size=7,
        max_overflow=2,
        pool_timeout_seconds=3.5,
        connect_timeout_seconds=4,
        statement_timeout_seconds=2.5,
    )

    # When: building async engine kwargs for Postgres
    kwargs = _build_async_engine_kwargs(
        "postgresql+psycopg://user:password@localhost:5432/agent_control",
        config,
    )

    # Then: the engine is configured with a bounded, health-checked pool and timeouts
    assert kwargs == {
        "echo": False,
        "pool_pre_ping": True,
        "pool_size": 7,
        "max_overflow": 2,
        "pool_timeout": 3.5,
        "pool_reset_on_return": "rollback",
        "connect_args": {
            "connect_timeout": 4,
            "options": "-c statement_timeout=2500",
        },
    }


def test_build_async_engine_kwargs_uses_asyncpg_connect_args() -> None:
    # Given: timeout settings with an asyncpg driver URL
    config = AgentControlServerDatabaseConfig(
        connect_timeout_seconds=4,
        statement_timeout_seconds=2.5,
    )

    # When: building async engine kwargs for asyncpg
    kwargs = _build_async_engine_kwargs(
        "postgresql+asyncpg://user:password@localhost:5432/agent_control",
        config,
    )

    # Then: the timeouts are expressed as asyncpg connect args
    assert kwargs["connect_args"] == {
        "timeout": 4.0,
