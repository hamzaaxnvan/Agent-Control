"""Alembic coverage for Phase 0 control cleanup and audit backfill."""

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
PRE_MIGRATION_REVISION = "5f2b5f4e1a90"
MIGRATION_REVISION = "c1e9f9c4a1d2"
_BASE_DB_URL = make_url(db_config.get_url())

pytestmark = pytest.mark.skipif(
    _BASE_DB_URL.get_backend_name() != "postgresql",
    reason="Phase 0 Alembic migration tests require PostgreSQL.",
)


def _unrendered_template_payload() -> dict[str, Any]:
    return {
        "template": {
            "description": "Regex denial template",
            "parameters": {
                "pattern": {
                    "type": "regex_re2",
                    "label": "Pattern",
                },
            },
            "definition_template": {
                "description": "Template-backed control",
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "regex",
                        "config": {"pattern": {"$param": "pattern"}},
                    },
                },
                "action": {"decision": "deny"},
            },
        },
        "template_values": {},
    }


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


def _insert_policy(engine: Engine, *, name: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    """
                    INSERT INTO policies (name)
                    VALUES (:name)
                    RETURNING id
                    """
                ),
                {"name": name},
            ).scalar_one()
        )


def _insert_agent(engine: Engine, *, name: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO agents (name, data)
                VALUES (:name, '{}'::jsonb)
                """
            ),
            {"name": name},
        )


def _associate_policy_control(engine: Engine, *, policy_id: int, control_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO policy_controls (policy_id, control_id)
                VALUES (:policy_id, :control_id)
                """
            ),
            {"policy_id": policy_id, "control_id": control_id},
        )


def _associate_agent_control(engine: Engine, *, agent_name: str, control_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO agent_controls (agent_name, control_id)
                VALUES (:agent_name, :control_id)
                """
            ),
            {"agent_name": agent_name, "control_id": control_id},
        )


def _fetch_control(engine: Engine, control_id: int) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, data, deleted_at
                FROM controls
                WHERE id = :id
                """
            ),
            {"id": control_id},
        ).mappings().one()
        return dict(row)


def _fetch_versions(engine: Engine, control_id: int) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT version_num, event_type, snapshot, note
                FROM control_versions
                WHERE control_id = :control_id
                ORDER BY version_num
                """
            ),
            {"control_id": control_id},
        ).mappings()
        return [dict(row) for row in rows]


def _policy_control_count(engine: Engine, control_id: int) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM policy_controls WHERE control_id = :control_id"
                ),
                {"control_id": control_id},
            ).scalar_one()
        )


def _agent_control_count(engine: Engine, control_id: int) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM agent_controls WHERE control_id = :control_id"
                ),
                {"control_id": control_id},
            ).scalar_one()
        )


@pytest.fixture
def temp_db_url() -> str:
    temp_db_name = f"agent_control_phase0_{uuid.uuid4().hex[:12]}"
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
