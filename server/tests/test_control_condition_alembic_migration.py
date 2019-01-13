"""Alembic coverage for legacy control condition normalization."""

from __future__ import annotations

import asyncio
import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_control_server.config import db_config
from agent_control_server.db import get_async_db
from alembic import command

from .utils import VALID_CONTROL_PAYLOAD

SERVER_DIR = Path(__file__).resolve().parents[1]
PRE_MIGRATION_REVISION = "4b8c7d4a1f31"
MIGRATION_REVISION = "9f2f5a4e6c1b"
TEST_ADMIN_API_KEY = "test-admin-key-12345"
_BASE_DB_URL = make_url(db_config.get_url())

pytestmark = pytest.mark.skipif(
    _BASE_DB_URL.get_backend_name() != "postgresql",
    reason="Control condition Alembic migration tests require PostgreSQL.",
)


def _legacy_control_payload() -> dict[str, Any]:
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["selector"] = payload["condition"]["selector"]
    payload["evaluator"] = payload["condition"]["evaluator"]
    payload.pop("condition")
    return payload


def _composite_control_payload() -> dict[str, Any]:
    first_leaf = deepcopy(VALID_CONTROL_PAYLOAD["condition"])
    second_leaf = {
        "selector": {"path": "output"},
        "evaluator": {"name": "regex", "config": {"pattern": "blocked"}},
    }
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["condition"] = {"and": [first_leaf, second_leaf]}
    return payload


def _insert_control(engine: Engine, *, name: str, data: Any) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    """
                    INSERT INTO controls (name, data)
                    VALUES (:name, CAST(:data AS JSONB))
                    RETURNING id
                    """
                ),
                {"name": name, "data": json.dumps(data)},
            ).scalar_one()
        )


def _fetch_controls(engine: Engine) -> list[tuple[int, str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, name, data FROM controls ORDER BY id")
        ).mappings()
        return [(int(row["id"]), str(row["name"]), row["data"]) for row in rows]


def _fetch_control_data(engine: Engine, control_id: int) -> Any:
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT data FROM controls WHERE id = :id"),
            {"id": control_id},
        ).scalar_one()


def _current_revision(engine: Engine) -> str | None:
    with engine.begin() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


@pytest.fixture
def temp_db_url() -> str:
    temp_db_name = f"agent_control_migration_{uuid.uuid4().hex[:12]}"
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


@pytest.fixture
def upgrade_to(alembic_config: Config):
    def _upgrade(revision: str, *, sql: bool = False) -> None:
        command.upgrade(alembic_config, revision, sql=sql)

    return _upgrade


def test_upgrade_noops_when_no_legacy_rows_exist(
    upgrade_to,
    temp_engine: Engine,
) -> None:
    upgrade_to(PRE_MIGRATION_REVISION)
    _insert_control(temp_engine, name="canonical", data=deepcopy(VALID_CONTROL_PAYLOAD))
