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
