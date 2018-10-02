"""Database-level coverage for namespace-scoped uniqueness and same-namespace
foreign key enforcement.

These tests use raw SQL against the configured test database so they exercise
the actual constraints created by the migration (and reflected by
``Base.metadata.create_all`` in tests).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


def _agent_name() -> str:
    """Return a name that satisfies the agents check constraints."""
    suffix = uuid.uuid4().hex[:12]
    return f"agent-{suffix}"


@pytest.fixture
def clean_tables(db_engine: Engine):
    """Truncate the data-model tables before and after each test."""

    def _truncate() -> None:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE TABLE control_bindings, agent_controls, "
                    "agent_policies, policy_controls, agents, policies, "
                    "controls RESTART IDENTITY CASCADE"
                )
            )

    _truncate()
    yield
    _truncate()


def _insert_agent(engine: Engine, *, namespace_key: str, name: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agents (namespace_key, name, data) "
                "VALUES (:ns, :name, '{}'::jsonb)"
            ),
            {"ns": namespace_key, "name": name},
        )


def _insert_control(
    engine: Engine,
    *,
    namespace_key: str,
    name: str,
    deleted: bool = False,
) -> int:
    with engine.begin() as conn:
        deleted_at = dt.datetime.now(dt.UTC) if deleted else None
        return int(
            conn.execute(
                text(
                    "INSERT INTO controls (namespace_key, name, data, deleted_at) "
                    "VALUES (:ns, :name, '{}'::jsonb, :deleted_at) "
                    "RETURNING id"
                ),
                {
                    "ns": namespace_key,
                    "name": name,
                    "deleted_at": deleted_at,
                },
            ).scalar_one()
        )


def _insert_policy(engine: Engine, *, namespace_key: str, name: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO policies (namespace_key, name) "
                    "VALUES (:ns, :name) RETURNING id"
                ),
                {"ns": namespace_key, "name": name},
            ).scalar_one()
        )


# Cross-namespace uniqueness (the same natural key may appear in different
# namespaces).


def test_agents_same_name_different_namespaces_allowed(
    db_engine: Engine, clean_tables: None
) -> None:
    name = _agent_name()
    _insert_agent(db_engine, namespace_key="ns-one", name=name)
    _insert_agent(db_engine, namespace_key="ns-two", name=name)


def test_controls_same_live_name_different_namespaces_allowed(
    db_engine: Engine, clean_tables: None
) -> None:
    _insert_control(db_engine, namespace_key="ns-one", name="pii-blocker")
    _insert_control(db_engine, namespace_key="ns-two", name="pii-blocker")


def test_policies_same_name_different_namespaces_allowed(
    db_engine: Engine, clean_tables: None
) -> None:
    _insert_policy(db_engine, namespace_key="ns-one", name="default-policy")
    _insert_policy(db_engine, namespace_key="ns-two", name="default-policy")

