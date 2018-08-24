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
