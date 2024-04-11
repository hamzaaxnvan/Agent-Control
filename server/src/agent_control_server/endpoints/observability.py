"""Observability API endpoints.

This module provides endpoints for:
1. Event ingestion (POST /events) - SDK sends batched events
2. Event queries (POST /events/query) - Query raw events by trace_id, etc.
3. Stats (GET /stats) - Aggregated statistics for dashboards

All endpoints declare operation-based auth dependencies.

Dependencies are stored on app.state during server lifespan (see main.py):
- app.state.event_ingestor: EventIngestor
- app.state.event_store: EventStore
"""

import logging
import time
from typing import Literal, cast

from agent_control_models import (
    BatchEventsRequest,
    BatchEventsResponse,
    ControlStatsResponse,
    EventQueryRequest,
    EventQueryResponse,
    StatsResponse,
    StatsTotals,
)
from fastapi import APIRouter, Depends, Request

from ..auth_framework import Operation, Principal, require_operation
from ..observability.ingest.base import EventIngestor
from ..observability.store.base import (
    EventStore,
    TimeRange,
    get_bucket_size,
    parse_time_range,
)
from ..services.agent_names import normalize_agent_name_or_422

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/observability",
    tags=["observability"],
)


# =============================================================================
# Dependency Injection (via app.state)
# =============================================================================


def get_event_ingestor(request: Request) -> EventIngestor:
    """Get the event ingestor from app.state."""
    ingestor = getattr(request.app.state, "event_ingestor", None)
    if ingestor is None:
        raise RuntimeError("EventIngestor not initialized - check server startup")
    return cast(EventIngestor, ingestor)


