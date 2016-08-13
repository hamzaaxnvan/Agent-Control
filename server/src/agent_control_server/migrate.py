"""Run bundled Alembic migrations for agent-control-server.

Exposed as the ``agent-control-migrate`` console script. The wheel ships
its Alembic config and migration scripts under the package so this
command works in any install location (Docker, venv, system Python).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool

import agent_control_server
from agent_control_server.config import db_config

LOGGER = logging.getLogger(__name__)
_MIGRATION_LOCK_CLASS_ID = 0x4143544C  # "ACTL"
_MIGRATION_LOCK_OBJECT_ID = 0x4D494752  # "MIGR"
_MIGRATION_LOCK_POLL_SECONDS = 2.0
_DEFAULT_MIGRATION_LOCK_TIMEOUT_SECONDS = 600.0
_MIGRATION_LOCK_TIMEOUT_ENV = "AGENT_CONTROL_MIGRATION_LOCK_TIMEOUT_SECONDS"
_MIGRATION_LOCK_PARAMS = {
    "class_id": _MIGRATION_LOCK_CLASS_ID,
    "object_id": _MIGRATION_LOCK_OBJECT_ID,
}


def _bundled_config() -> Config:
    pkg_dir = Path(agent_control_server.__file__).parent
    ini_path = pkg_dir / "_alembic.ini"
    alembic_dir = pkg_dir / "_alembic"
    if not ini_path.exists() or not alembic_dir.exists():
        raise RuntimeError(
            "Bundled Alembic resources not found. Expected "
            f"{ini_path} and {alembic_dir}. The installed wheel is missing "
            "migration assets."
        )
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(alembic_dir).replace("%", "%%"))
    return cfg


@contextmanager
def _runtime_bundled_config() -> Iterator[Config]:
    cfg = _bundled_config()
    if not isinstance(cfg, Config):
        yield cast(Config, cfg)
        return

    bundled_script_location = cfg.get_main_option("script_location")
    if bundled_script_location is None:
        raise RuntimeError("Bundled Alembic script_location is not configured.")

    with tempfile.TemporaryDirectory(prefix="agent-control-alembic-") as tmp:
        script_location = Path(tmp) / "_alembic"
        shutil.copytree(bundled_script_location, script_location)
        for injected_init in (script_location / "versions").rglob("__init__.py"):
            injected_init.unlink()
        cfg.set_main_option("script_location", str(script_location).replace("%", "%%"))
        yield cfg


def _migration_url(cfg: Config) -> str:
    configured_url = cfg.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return db_config.get_url()


def _migration_lock_timeout_seconds() -> float:
    raw_timeout = os.getenv(_MIGRATION_LOCK_TIMEOUT_ENV)
    if raw_timeout is None:
        return _DEFAULT_MIGRATION_LOCK_TIMEOUT_SECONDS

    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise RuntimeError(f"{_MIGRATION_LOCK_TIMEOUT_ENV} must be a number.") from exc

    if timeout <= 0:
        raise RuntimeError(f"{_MIGRATION_LOCK_TIMEOUT_ENV} must be greater than zero.")
    return timeout


def _acquire_migration_lock(connection: Connection, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    logged_wait = False

    while True:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:class_id, :object_id)"),
                _MIGRATION_LOCK_PARAMS,
            ).scalar_one()
        )
        if acquired:
            connection.commit()
            LOGGER.info("Acquired Agent Control migration advisory lock.")
            return
