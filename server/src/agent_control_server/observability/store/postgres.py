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
        *,
        control_id: int | None = None,
        include_timeseries: bool = False,
        bucket_size: timedelta | None = None,
        namespace_key: str,
    ) -> StatsResult:
        """Query stats aggregated at query time from raw events.

        Optimized single-query implementation that fetches both per-control stats
        and time-series data in one database round-trip using a CTE.

        For time-series, uses generate_series to create all bucket timestamps
        and LEFT JOINs with aggregated data to include empty buckets.

        Args:
            agent_name: identifier of the agent to query stats for
            time_range: Time range to aggregate over (from now)
            control_id: Optional control ID to filter by
            include_timeseries: Whether to include time-series data
            bucket_size: Bucket size for time-series (required if include_timeseries=True)
            namespace_key: Namespace whose events should be queried

        Returns:
            StatsResult with per-control and total statistics
        """
        now = datetime.now(UTC)
        cutoff = now - time_range

        params: dict = {
            "namespace_key": namespace_key,
            "agent_name": agent_name,
            "cutoff": cutoff,
        }

        control_filter = ""
        if control_id is not None:
            control_filter = "AND (data->>'control_id')::int = :control_id"
            params["control_id"] = control_id

        # Build combined query with CTE
        if include_timeseries and bucket_size:
            bucket_interval = self._timedelta_to_interval(bucket_size)
            params["bucket_interval"] = bucket_interval
            params["now"] = now

            # Single query that returns both per-control stats and time-series
            # Uses UNION ALL with a discriminator column
            query = text(f"""
                WITH filtered_events AS (
                    SELECT timestamp, data
                    FROM control_execution_events
                    WHERE namespace_key = :namespace_key
                      AND agent_name = :agent_name
                      AND timestamp >= :cutoff
                      {control_filter}
                ),
                -- Per-control aggregation
                control_stats AS (
                    SELECT
                        'control' as query_type,
                        (data->>'control_id')::int as control_id,
                        data->>'control_name' as control_name,
                        NULL::timestamptz as bucket,
                        {SQL_STATS_AGGREGATIONS}
                    FROM filtered_events
                    GROUP BY data->>'control_id', data->>'control_name'
                ),
                -- Generate all bucket timestamps
                all_buckets AS (
                    SELECT generate_series(
                        :cutoff,
                        :now - CAST(:bucket_interval AS interval),
                        CAST(:bucket_interval AS interval)
                    ) as bucket
                ),
                -- Time-series aggregation (only buckets with data)
                bucket_stats AS (
                    SELECT
                        date_bin(CAST(:bucket_interval AS interval), timestamp, :cutoff) as bucket,
                        {SQL_STATS_AGGREGATIONS}
                    FROM filtered_events
                    GROUP BY date_bin(CAST(:bucket_interval AS interval), timestamp, :cutoff)
                ),
                -- Join with all buckets to fill empty ones
                timeseries AS (
                    SELECT
                        'timeseries' as query_type,
                        NULL::int as control_id,
                        NULL::text as control_name,
                        ab.bucket,
                        COALESCE(bs.execution_count, 0) as execution_count,
                        COALESCE(bs.match_count, 0) as match_count,
                        COALESCE(bs.non_match_count, 0) as non_match_count,
                        COALESCE(bs.error_count, 0) as error_count,
                        COALESCE(bs.deny_count, 0) as deny_count,
                        COALESCE(bs.steer_count, 0) as steer_count,
                        COALESCE(bs.observe_count, 0) as observe_count,
                        bs.avg_confidence,
                        bs.avg_duration_ms
                    FROM all_buckets ab
                    LEFT JOIN bucket_stats bs ON ab.bucket = bs.bucket
                )
                -- Return control stats first, then timeseries
                -- Wrap in subquery to allow ORDER BY with expressions
                SELECT * FROM (
                    SELECT * FROM control_stats
                    UNION ALL
                    SELECT * FROM timeseries
                ) combined
                ORDER BY query_type DESC, COALESCE(bucket, '1970-01-01'::timestamptz) ASC
            """)
        else:
            # Simple query without time-series
            query = text(f"""
                SELECT
                    'control' as query_type,
                    (data->>'control_id')::int as control_id,
                    data->>'control_name' as control_name,
                    NULL::timestamptz as bucket,
                    {SQL_STATS_AGGREGATIONS}
                FROM control_execution_events
                WHERE namespace_key = :namespace_key
                  AND agent_name = :agent_name
                  AND timestamp >= :cutoff
                  {control_filter}
                GROUP BY data->>'control_id', data->>'control_name'
                ORDER BY execution_count DESC
            """)

        async with self.session_maker() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()

        # Parse results - control stats first, then timeseries
        stats = []
        timeseries: list[TimeseriesBucket] | None = None
        total_executions = 0
        total_matches = 0
        total_non_matches = 0
        total_errors = 0
        action_counts: dict[str, int] = {"deny": 0, "steer": 0, "observe": 0}

        for row in rows:
            if row.query_type == "control":
                control_stats = ControlStats(
                    control_id=row.control_id,
                    control_name=row.control_name,
                    execution_count=row.execution_count,
                    match_count=row.match_count,
                    non_match_count=row.non_match_count,
                    error_count=row.error_count,
                    deny_count=row.deny_count,
                    steer_count=row.steer_count,
                    observe_count=row.observe_count,
                    avg_confidence=row.avg_confidence or 0.0,
                    avg_duration_ms=row.avg_duration_ms,
                )
                stats.append(control_stats)

                total_executions += row.execution_count
                total_matches += row.match_count
                total_non_matches += row.non_match_count
                total_errors += row.error_count
                action_counts["deny"] += row.deny_count
                action_counts["steer"] += row.steer_count
                action_counts["observe"] += row.observe_count

            elif row.query_type == "timeseries":
                if timeseries is None:
                    timeseries = []

