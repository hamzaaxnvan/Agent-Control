"""Reset the configured SDK test database to an empty schema."""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text

from agent_control_server.config import db_config


def _ensure_postgres_database_exists() -> None:
    admin_url = (
        f"postgresql+{db_config.driver}://{db_config.user}:{db_config.password}@"
        f"{db_config.host}:{db_config.port}/postgres"
    )
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_config.database},
        ).scalar()
        if not exists:
            database_name = db_config.database.replace('"', '""')
            conn.execute(text(f'CREATE DATABASE "{database_name}"'))
