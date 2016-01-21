import logging
from collections.abc import AsyncGenerator
from typing import Any

from prometheus_client import Gauge
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from .config import AgentControlServerDatabaseConfig, db_config

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Async SQLAlchemy setup for PostgreSQL
db_url = db_config.get_url()

SQLALCHEMY_CHECKED_OUT_CONNECTIONS = Gauge(
    "agent_control_server_sqlalchemy_checked_out_connections",
    "Number of checked out SQLAlchemy connections.",
    ["pool_name"],
    multiprocess_mode="livesum",
)


def _supports_queue_pool_config(url: str) -> bool:
    """Return whether SQLAlchemy QueuePool kwargs should be applied for this URL."""
    return make_url(url).get_backend_name() != "sqlite"


def _build_connect_args(
    url: str,
    config: AgentControlServerDatabaseConfig,
) -> dict[str, Any]:
    """Build driver-level connect args bounding connection setup and statement runtime.

    Pool timeouts only bound how long a request waits for a connection; these
    args bound how long a connection takes to establish and how long any one
    statement may hold it. Drivers without known timeout args get none.
    """
    driver = make_url(url).get_driver_name()
    statement_timeout_ms = int(config.statement_timeout_seconds * 1000)
    if driver == "psycopg":
        connect_args: dict[str, Any] = {"connect_timeout": config.connect_timeout_seconds}
        if statement_timeout_ms:
            connect_args["options"] = f"-c statement_timeout={statement_timeout_ms}"
        return connect_args
    if driver == "asyncpg":
        connect_args = {"timeout": float(config.connect_timeout_seconds)}
        if statement_timeout_ms:
            connect_args["server_settings"] = {"statement_timeout": str(statement_timeout_ms)}
        return connect_args
    return {}


def _build_async_engine_kwargs(
    url: str,
    config: AgentControlServerDatabaseConfig,
) -> dict[str, Any]:
    """Build async SQLAlchemy engine kwargs from database config."""
    kwargs: dict[str, Any] = {"echo": False}
    if not _supports_queue_pool_config(url):
        return kwargs

    kwargs.update(
        pool_pre_ping=True,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_timeout=config.pool_timeout_seconds,
        pool_reset_on_return="rollback",
    )
    connect_args = _build_connect_args(url, config)
    if connect_args:
