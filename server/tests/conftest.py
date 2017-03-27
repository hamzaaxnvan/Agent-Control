import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from agent_control_engine import discover_evaluators
from agent_control_server.config import auth_settings, db_config
from agent_control_server.db import Base
from agent_control_server.main import app as fastapi_app

import agent_control_server.models  # ensure models are imported so tables are registered

# Discover evaluators at test session start
discover_evaluators()

# Test API keys
TEST_API_KEY = "test-api-key-12345"
TEST_ADMIN_API_KEY = "test-admin-key-12345"

# Create sync engine for tests (schema creation/cleanup)
engine = create_engine(db_config.get_url(), echo=False)

# Create async engine for async tests
async_engine = create_async_engine(db_config.get_url(), echo=False)
AsyncSessionTest = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _truncate_all_tables() -> None:
    """Clear all tables in the configured test database."""
    with engine.begin() as conn:
        schema = "public" if conn.dialect.name == "postgresql" else None
        table_names = inspect(conn).get_table_names(schema=schema)
        if not table_names:
            return

        if conn.dialect.name == "postgresql":
            qualified_tables = ", ".join(f'"{schema}"."{table_name}"' for table_name in table_names)
            conn.execute(text(f"TRUNCATE TABLE {qualified_tables} RESTART IDENTITY CASCADE"))
            return

        reflected_metadata = MetaData()
        reflected_metadata.reflect(bind=conn)
        for table in reversed(reflected_metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(scope="session")
def db_engine():
    """Provide the sqlalchemy engine for tests."""
    return engine


@pytest.fixture(scope="session")
def app():
    """Provide the FastAPI app."""
    return fastapi_app


@pytest.fixture(scope="session", autouse=True)
