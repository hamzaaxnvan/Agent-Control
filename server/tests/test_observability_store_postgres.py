from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agent_control_models.observability import ControlExecutionEvent, EventQueryRequest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_control_server.models import DEFAULT_NAMESPACE_KEY
from agent_control_server.observability.store.postgres import PostgresEventStore

from .conftest import async_engine, engine


@pytest.fixture(autouse=True)
def clear_event_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM control_execution_events"))
    yield


def _event(
    *,
    agent_name,
    control_id: int,
    action: str,
    matched: bool,
    timestamp: datetime,
    trace_id: str,
    span_id: str = "b" * 16,
    control_execution_id: str | None = None,
    check_stage: str = "pre",
    applies_to: str = "llm_call",
) -> ControlExecutionEvent:
    return ControlExecutionEvent(
        trace_id=trace_id,
        span_id=span_id,
        agent_name=agent_name,
        control_id=control_id,
        control_name=f"control-{control_id}",
        check_stage=check_stage,
        applies_to=applies_to,
        action=action,
        matched=matched,
        confidence=0.8,
        timestamp=timestamp,
        control_execution_id=control_execution_id or str(uuid4()),
    )


@pytest.mark.asyncio
async def test_postgres_event_store_query_events_and_stats() -> None:
    # Given: a Postgres-backed store and a set of events
    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    store = PostgresEventStore(session_maker)

    agent_name = f"agent-{uuid4().hex[:12]}"
    now = datetime.now(UTC)

    events = [
        _event(
            agent_name=agent_name,
            control_id=1,
            action="observe",
            matched=True,
            timestamp=now - timedelta(seconds=10),
            trace_id="a" * 32,
        ),
        _event(
            agent_name=agent_name,
            control_id=2,
            action="deny",
            matched=False,
            timestamp=now - timedelta(seconds=5),
            trace_id="b" * 32,
        ),
        _event(
            agent_name=agent_name,
            control_id=1,
            action="observe",
            matched=True,
            timestamp=now,
            trace_id="a" * 32,
        ),
    ]

    # When: storing events
    await store.store(events, namespace_key=DEFAULT_NAMESPACE_KEY)

    # When: querying events filtered by control_id
    query = EventQueryRequest(agent_name=agent_name, control_ids=[1], limit=10, offset=0)
    resp = await store.query_events(query, namespace_key=DEFAULT_NAMESPACE_KEY)
    # Then: only matching events are returned
    assert resp.total == 2
    assert all(e.control_id == 1 for e in resp.events)

    # When: querying events filtered by trace_id
    query = EventQueryRequest(trace_id="a" * 32, limit=10, offset=0)
    resp = await store.query_events(query, namespace_key=DEFAULT_NAMESPACE_KEY)
    # Then: only matching events are returned
    assert resp.total == 2
    assert all(e.trace_id == "a" * 32 for e in resp.events)

    # When: querying stats
    stats = await store.query_stats(
        agent_name, timedelta(hours=1), namespace_key=DEFAULT_NAMESPACE_KEY
    )
    # Then: totals and action counts are aggregated correctly
    assert stats.total_executions == 3
    assert stats.total_matches == 2
    assert stats.total_non_matches == 1
    assert stats.total_errors == 0
    assert stats.action_counts == {"observe": 2}

    # When: querying stats with a control filter
    filtered_stats = await store.query_stats(
        agent_name,
        timedelta(hours=1),
        control_id=1,
        namespace_key=DEFAULT_NAMESPACE_KEY,
    )
    # Then: only the requested control is returned
    assert len(filtered_stats.stats) == 1
    assert filtered_stats.stats[0].control_id == 1


@pytest.mark.asyncio
async def test_postgres_event_store_scopes_queries_by_namespace() -> None:
    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    store = PostgresEventStore(session_maker)

    agent_name = f"agent-{uuid4().hex[:12]}"
    now = datetime.now(UTC)
    event_a = _event(
        agent_name=agent_name,
        control_id=1,
        action="observe",
        matched=True,
        timestamp=now,
        trace_id="a" * 32,
    )
    event_b = _event(
        agent_name=agent_name,
        control_id=2,
        action="deny",
        matched=True,
        timestamp=now,
        trace_id="b" * 32,
    )

    await store.store([event_a], namespace_key="tenant-a")
    await store.store([event_b], namespace_key="tenant-b")

    query = EventQueryRequest(agent_name=agent_name, limit=10, offset=0)
    events_a = await store.query_events(query, namespace_key="tenant-a")
    stats_a = await store.query_stats(
        agent_name,
        timedelta(hours=1),
        namespace_key="tenant-a",
    )

    assert [event.control_id for event in events_a.events] == [1]
    assert stats_a.total_executions == 1
    assert stats_a.stats[0].control_id == 1


@pytest.mark.asyncio
async def test_postgres_event_store_idempotency_is_scoped_by_namespace() -> None:
    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    store = PostgresEventStore(session_maker)

    shared_execution_id = str(uuid4())
    agent_name = f"agent-{uuid4().hex[:12]}"
    now = datetime.now(UTC)
    event_a = _event(
        control_execution_id=shared_execution_id,
        agent_name=agent_name,
        control_id=1,
        action="observe",
        matched=True,
        timestamp=now,
