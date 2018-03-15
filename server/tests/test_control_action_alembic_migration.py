"""Alembic coverage for collapsing advisory actions to observe."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from agent_control_server.config import db_config

from .utils import VALID_CONTROL_PAYLOAD

SERVER_DIR = Path(__file__).resolve().parents[1]
PRE_MIGRATION_REVISION = "8b23d645f86d"
MIGRATION_REVISION = "5f2b5f4e1a90"
_BASE_DB_URL = make_url(db_config.get_url())

pytestmark = pytest.mark.skipif(
    _BASE_DB_URL.get_backend_name() != "postgresql",
    reason="Control action Alembic migration tests require PostgreSQL.",
)


def _control_payload(action: str) -> dict[str, Any]:
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["action"]["decision"] = action
    return payload


def _insert_control(engine: Engine, *, name: str, data: dict[str, Any]) -> int:
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


def _fetch_control_data(engine: Engine, control_id: int) -> Any:
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT data FROM controls WHERE id = :id"),
            {"id": control_id},
        ).scalar_one()
