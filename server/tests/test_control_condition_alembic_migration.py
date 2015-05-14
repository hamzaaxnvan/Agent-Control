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
