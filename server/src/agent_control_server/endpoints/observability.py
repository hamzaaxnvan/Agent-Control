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


def get_event_store(request: Request) -> EventStore:
    """Get the event store from app.state."""
    store = getattr(request.app.state, "event_store", None)
    if store is None:
        raise RuntimeError("EventStore not initialized - check server startup")
    return cast(EventStore, store)


# =============================================================================
# Event Ingestion
# =============================================================================


@router.post(
    "/events",
    status_code=202,
    response_model=BatchEventsResponse,
)
async def ingest_events(
    request: BatchEventsRequest,
    ingestor: EventIngestor = Depends(get_event_ingestor),
    principal: Principal = Depends(require_operation(Operation.OBSERVABILITY_WRITE)),
) -> BatchEventsResponse:
    """
    Ingest batched control execution events.

    Events are stored directly to the database with ~5-20ms latency.

    Args:
        request: Batch of events to ingest
        ingestor: Event ingestor (injected)

    Returns:
        BatchEventsResponse with counts of received/processed/dropped
    """
    start_time = time.perf_counter()

    result = await ingestor.ingest(
        request.events,
        namespace_key=principal.namespace_key,
    )

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.debug(
        f"Ingested {result.received} events "
        f"(processed={result.processed}, dropped={result.dropped}) in {duration_ms:.2f}ms"
    )

    # Determine status
    status: Literal["queued", "partial", "failed"]
    if result.dropped == 0:
        status = "queued"  # Keep "queued" for API compatibility
    elif result.processed > 0:
        status = "partial"
    else:
        status = "failed"

    return BatchEventsResponse(
        received=result.received,
        enqueued=result.processed,  # Map to "enqueued" for API compatibility
        dropped=result.dropped,
