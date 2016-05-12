from __future__ import annotations

from pathlib import Path

import agent_control_server
from agent_control_server import migrate
from alembic.config import Config


class _FakeResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class _FakeConnection:
    def __init__(self, lock_results: list[bool]) -> None:
        self.lock_results = lock_results
        self.statements: list[str] = []
        self.commits = 0

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object, params: object) -> _FakeResult:
        statement_text = str(statement)
        self.statements.append(statement_text)
        if "pg_try_advisory_lock" in statement_text:
            return _FakeResult(self.lock_results.pop(0))
        if "pg_advisory_unlock" in statement_text:
            return _FakeResult(True)
        raise AssertionError(f"unexpected SQL statement: {statement_text}")

    def commit(self) -> None:
        self.commits += 1


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.disposed = False

    def connect(self) -> _FakeConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def test_bundled_config_omits_injected_version_init(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "agent_control_server"
    versions_dir = package_dir / "_alembic" / "versions"
    versions_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "_alembic.ini").write_text(
        "[alembic]\nscript_location = _alembic\n",
        encoding="utf-8",
    )
    (package_dir / "_alembic" / "env.py").write_text("", encoding="utf-8")
