"""Unit tests for the bundled-migrations entry point.

These do not run migrations against a database. They verify the wheel-bundling
contract: the console script resolves to the right callable, dispatches
correctly to Alembic commands, and the bundled-config helper can load the
packaged migration layout.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock

import pytest
from agent_control_server import migrate
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.fixture
def stub_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    """Replace runtime config building with a lightweight Alembic config.

    Lets dispatch tests verify which Alembic command was called and
    what config was passed without touching real migration assets or DB locks.
    """
    sentinel = Config()
    sentinel.set_main_option("sqlalchemy.url", "sqlite:///agent-control-test.db")

    @contextmanager
    def fake_runtime_bundled_config() -> Iterator[Config]:
        yield sentinel

    monkeypatch.setattr(migrate, "_runtime_bundled_config", fake_runtime_bundled_config)
    return sentinel


def _patch_command(monkeypatch: pytest.MonkeyPatch, name: str) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(migrate.command, name, mock)
    return mock


def test_main_default_runs_upgrade_head(
    stub_config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    upgrade = _patch_command(monkeypatch, "upgrade")
    rc = migrate.main([])
    assert rc == 0
    upgrade.assert_called_once_with(stub_config, "head", sql=False)


def test_main_bare_upgrade_runs_upgrade_head(
    stub_config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    upgrade = _patch_command(monkeypatch, "upgrade")
    rc = migrate.main(["upgrade"])
    assert rc == 0
    upgrade.assert_called_once_with(stub_config, "head", sql=False)
