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
        "server_settings": {"statement_timeout": "2500"},
    }


def test_build_async_engine_kwargs_can_disable_statement_timeout() -> None:
    # Given: the statement timeout is disabled
    config = AgentControlServerDatabaseConfig(
        connect_timeout_seconds=5,
        statement_timeout_seconds=0,
    )

    # When: building async engine kwargs for Postgres
    kwargs = _build_async_engine_kwargs(
        "postgresql+psycopg://user:password@localhost:5432/agent_control",
        config,
    )

    # Then: no statement timeout option is passed to the driver
    assert kwargs["connect_args"] == {"connect_timeout": 5}


def test_build_async_engine_kwargs_skips_pool_config_for_sqlite() -> None:
    # Given: custom pool settings with a SQLite URL
    config = AgentControlServerDatabaseConfig(
        pool_size=7,
        max_overflow=2,
        pool_timeout_seconds=3.5,
    )

    # When: building async engine kwargs for SQLite
    kwargs = _build_async_engine_kwargs("sqlite+aiosqlite:///tmp/agent-control.db", config)

    # Then: SQLite keeps SQLAlchemy's default local-dev pool behavior
    assert kwargs == {"echo": False}


def test_build_async_engine_kwargs_logs_when_driver_timeout_args_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given: a non-sqlite backend whose driver has no known timeout connect args
    config = AgentControlServerDatabaseConfig()

    # When: building async engine kwargs
    with caplog.at_level(logging.DEBUG, logger="agent_control_server.db"):
        kwargs = _build_async_engine_kwargs(
            "postgresql+someasync://user:password@localhost:5432/agent_control",
            config,
        )

