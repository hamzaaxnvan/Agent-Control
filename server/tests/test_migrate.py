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
