"""PostgreSQL event store implementation.

This module provides the PostgresEventStore, which stores raw events
in PostgreSQL with JSONB and performs aggregation at query time.

Performance characteristics:
- store(): ~5-10ms for batch of 100 events
- query_stats(): ~10-200ms depending on time range and event count
- query_events(): ~10-50ms with index-backed filtering
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from agent_control_models.actions import ActionDecision, expand_action_filter
from agent_control_models.observability import (
    ControlExecutionEvent,
    ControlStats,
    EventQueryRequest,
    EventQueryResponse,
    TimeseriesBucket,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .base import EventStore, StatsResult

logger = logging.getLogger(__name__)


# =============================================================================
# SQL Aggregation Expressions
# =============================================================================
# These constants define the JSONB-based aggregation expressions used in stats
# queries. Centralizing them ensures consistency and makes maintenance easier.

# Count expressions
SQL_EXECUTION_COUNT = "COUNT(*)"

SQL_MATCH_COUNT = """SUM(CASE WHEN (data->>'matched')::boolean
    AND data->>'error_message' IS NULL THEN 1 ELSE 0 END)"""

SQL_NON_MATCH_COUNT = """SUM(CASE WHEN NOT (data->>'matched')::boolean
    AND data->>'error_message' IS NULL THEN 1 ELSE 0 END)"""

SQL_ERROR_COUNT = """SUM(CASE WHEN data->>'error_message' IS NOT NULL
    THEN 1 ELSE 0 END)"""

# Historical event rows intentionally preserve legacy advisory action names
# (`allow`, `warn`, `log`). Query-time reads normalize those stored values into the
# canonical `observe` bucket instead of rewriting past event payloads in-place.
_OBSERVE_ACTION_FILTER: tuple[ActionDecision, ...] = ("observe",)
_OBSERVE_ACTION_SQL_VALUES = ", ".join(
    f"'{action}'" for action in expand_action_filter(_OBSERVE_ACTION_FILTER)
)

# Action count expressions (only count when matched)
SQL_DENY_COUNT = """SUM(CASE WHEN (data->>'matched')::boolean
    AND data->>'action' = 'deny' THEN 1 ELSE 0 END)"""

SQL_STEER_COUNT = """SUM(CASE WHEN (data->>'matched')::boolean
    AND data->>'action' = 'steer' THEN 1 ELSE 0 END)"""

SQL_OBSERVE_COUNT = f"""SUM(CASE WHEN (data->>'matched')::boolean
    AND data->>'action' IN ({_OBSERVE_ACTION_SQL_VALUES}) THEN 1 ELSE 0 END)"""

# Average expressions
SQL_AVG_CONFIDENCE = "AVG((data->>'confidence')::float)"

SQL_AVG_DURATION = """AVG((data->>'execution_duration_ms')::float) FILTER (
    WHERE data->>'execution_duration_ms' IS NOT NULL)"""

# Combined aggregation columns (for SELECT statements)
SQL_STATS_AGGREGATIONS = f"""
    {SQL_EXECUTION_COUNT} as execution_count,
    {SQL_MATCH_COUNT} as match_count,
    {SQL_NON_MATCH_COUNT} as non_match_count,
    {SQL_ERROR_COUNT} as error_count,
    {SQL_DENY_COUNT} as deny_count,
    {SQL_STEER_COUNT} as steer_count,
    {SQL_OBSERVE_COUNT} as observe_count,
    {SQL_AVG_CONFIDENCE} as avg_confidence,
    {SQL_AVG_DURATION} as avg_duration_ms"""


class PostgresEventStore(EventStore):
    """PostgreSQL-based event store with JSONB storage and query-time aggregation.

    This implementation stores raw events with:
    - Indexed columns (control_execution_id, timestamp, agent_name) for efficient filtering
    - JSONB 'data' column containing the full event for flexible querying

    Stats are computed at query time from raw events, which is fast enough
    for most use cases (sub-200ms for 1-hour windows).

    Attributes:
        session_maker: SQLAlchemy async session maker
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """Initialize the store.

        Args:
            session_maker: SQLAlchemy async session maker
        """
        self.session_maker = session_maker

    async def store(
        self,
        events: list[ControlExecutionEvent],
        *,
        namespace_key: str,
    ) -> int:
        """Store raw events in PostgreSQL.

        Uses batch insert with ON CONFLICT DO NOTHING for idempotency.
        The simplified schema stores only a few indexed columns:
        - namespace_key (tenant partition)
        - control_execution_id (PK)
        - timestamp (indexed)
        - agent_name (indexed)
        - data (JSONB containing full event)

        Args:
            events: List of control execution events to store
            namespace_key: Namespace that owns the events

        Returns:
            Number of events successfully stored
        """
        if not events:
            return 0

        # Build values for batch insert.
        values = []
        for event in events:
            # Serialize the full event to JSONB
            event_data = event.model_dump(mode="json")

            values.append({
                "namespace_key": namespace_key,
                "control_execution_id": event.control_execution_id,
                "timestamp": event.timestamp,
                "agent_name": event.agent_name,
                "data": json.dumps(event_data),
            })

        async with self.session_maker() as session:
            # Batch insert with minimal indexed columns plus JSONB event data.
            await session.execute(
                text("""
                    INSERT INTO control_execution_events (
                        namespace_key, control_execution_id, timestamp, agent_name, data
                    ) VALUES (
                        :namespace_key, :control_execution_id, :timestamp, :agent_name,
                        CAST(:data AS JSONB)
                    )
                    ON CONFLICT (namespace_key, control_execution_id) DO NOTHING
                """),
                values,
            )
            await session.commit()

        logger.debug(f"Stored {len(events)} events")
        return len(events)

    async def query_stats(
        self,
        agent_name: str,
        time_range: timedelta,
