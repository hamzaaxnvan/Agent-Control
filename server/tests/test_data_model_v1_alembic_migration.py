"""Alembic coverage for the namespace scoping and control bindings migration."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from agent_control_server.config import db_config
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

SERVER_DIR = Path(__file__).resolve().parents[1]
PRE_MIGRATION_REVISION = "c1e9f9c4a1d2"
MIGRATION_REVISION = "a7f3b1e0d9c5"
OBSERVABILITY_NAMESPACE_REVISION = "b6f4c2d8e9a1"
CLONE_LINEAGE_REVISION = "e2b7f4a9c6d1"
SEED_IDENTITY_REVISION = "f3a1c8d7e2b4"
SEED_INDEX_REVISION = "d7e4a9b2c6f1"
_BASE_DB_URL = make_url(db_config.get_url())

pytestmark = pytest.mark.skipif(
    _BASE_DB_URL.get_backend_name() != "postgresql",
    reason="Alembic migration tests require PostgreSQL.",
)


@pytest.fixture
def temp_db_url() -> str:
    temp_db_name = f"agent_control_dmv1_{uuid.uuid4().hex[:12]}"
    admin_url = _BASE_DB_URL.set(database="postgres").render_as_string(hide_password=False)
    target_url = _BASE_DB_URL.set(database=temp_db_name).render_as_string(hide_password=False)

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{temp_db_name}"'))
    admin_engine.dispose()

    try:
        yield target_url
    finally:
        cleanup_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as conn:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :db_name AND pid <> pg_backend_pid()
                    """
                ),
                {"db_name": temp_db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{temp_db_name}"'))
        cleanup_engine.dispose()


@pytest.fixture
def alembic_config(temp_db_url: str) -> Config:
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", temp_db_url)
    return cfg


@pytest.fixture
def temp_engine(temp_db_url: str) -> Engine:
    engine = create_engine(temp_db_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


def _column_names(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _index_names(engine: Engine, table: str) -> set[str]:
    return {i["name"] for i in inspect(engine).get_indexes(table)}


def _foreign_key_names(engine: Engine, table: str) -> set[str]:
    return {fk["name"] for fk in inspect(engine).get_foreign_keys(table)}


def _unique_constraint_names(engine: Engine, table: str) -> set[str]:
    return {uc["name"] for uc in inspect(engine).get_unique_constraints(table)}


def _pk_columns(engine: Engine, table: str) -> list[str]:
    return list(inspect(engine).get_pk_constraint(table)["constrained_columns"])


def _assert_observability_namespace_schema(engine: Engine) -> None:
    assert "namespace_key" in _column_names(engine, "control_execution_events")
    assert _pk_columns(engine, "control_execution_events") == [
        "namespace_key",
        "control_execution_id",
    ]
    indexes = _index_names(engine, "control_execution_events")
    assert "ix_events_namespace_agent_time" in indexes
    assert "ix_events_agent_time" not in indexes


def _pg_index_definition(engine: Engine, index_name: str) -> str:
    with engine.begin() as conn:
        return str(
            conn.execute(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE tablename = 'controls' AND indexname = :index_name
                    """
                ),
                {"index_name": index_name},
            ).scalar_one()
        )


def _pg_index_is_valid(engine: Engine, index_name: str) -> bool:
    with engine.begin() as conn:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT pg_index.indisvalid
                    FROM pg_index
                    WHERE pg_index.indexrelid = to_regclass(:index_name)
                    """
                ),
                {"index_name": index_name},
            ).scalar_one()
        )


def _pg_constraint_definition(engine: Engine, constraint_name: str) -> tuple[str, str]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) AS definition, confdeltype
                FROM pg_constraint
                WHERE conname = :constraint_name
                """
            ),
            {"constraint_name": constraint_name},
        ).one()
        return str(row.definition), str(row.confdeltype)


