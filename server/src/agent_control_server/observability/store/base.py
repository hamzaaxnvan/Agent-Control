"""Base interfaces for event storage.

This module defines the EventStore ABC that all event stores must implement.
The interface supports raw event storage and query-time aggregation (no pre-aggregation).

Built-in implementations:
    - PostgresEventStore: Postgres with JSONB storage and query-time aggregation

Custom implementations users can create:
    - ClickhouseEventStore: Native JSON + columnar = fast aggregation
    - TimescaleDBEventStore: Time-series optimized Postgres extension
    - ElasticsearchEventStore: Full-text search capabilities
"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Literal

from agent_control_models.observability import (
    ControlExecutionEvent,
    ControlStats,
    EventQueryRequest,
    EventQueryResponse,
    TimeseriesBucket,
)
from pydantic import BaseModel, Field

# Type alias for time range literals
TimeRange = Literal["1m", "5m", "15m", "1h", "24h", "7d", "30d", "180d", "365d"]


class StatsResult(BaseModel):
    """Result of a stats query.

    Contains per-control statistics and totals, aggregated at query time
    from raw events.

    Invariant: total_executions = total_matches + total_non_matches + total_errors

    Matches have actions (deny, steer, observe) tracked in action_counts.
    sum(action_counts.values()) == total_matches

    Attributes:
        stats: List of per-control statistics
        total_executions: Total executions across all controls
        total_matches: Total matches across all controls (evaluator matched)
        total_non_matches: Total non-matches across all controls (evaluator didn't match)
        total_errors: Total errors across all controls (evaluation failed)
        action_counts: Breakdown of actions for matched executions
        timeseries: Optional time-series data points
    """

    stats: list[ControlStats] = Field(default_factory=list, description="Per-control statistics")
    total_executions: int = Field(default=0, ge=0, description="Total executions")
    total_matches: int = Field(default=0, ge=0, description="Total matches")
    total_non_matches: int = Field(default=0, ge=0, description="Total non-matches")
    total_errors: int = Field(default=0, ge=0, description="Total errors")
    action_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Action breakdown for matches: {deny, steer, observe}",
    )
    timeseries: list[TimeseriesBucket] | None = Field(
        default=None,
        description="Time-series data points (only when include_timeseries=true)",
    )


# Re-export query types from models for convenience
EventQuery = EventQueryRequest
EventQueryResult = EventQueryResponse


# Time range string to timedelta mapping
TIME_RANGE_MAP: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "180d": timedelta(days=180),
    "365d": timedelta(days=365),
}


def parse_time_range(time_range: TimeRange) -> timedelta:
    """Convert time range string to timedelta."""
    return TIME_RANGE_MAP[time_range]


# Bucket size mapping for time-series data
# Aims for 6-30 data points per time range for clean charts
BUCKET_SIZE_MAP: dict[str, timedelta] = {
