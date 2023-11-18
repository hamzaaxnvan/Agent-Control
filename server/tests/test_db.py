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
