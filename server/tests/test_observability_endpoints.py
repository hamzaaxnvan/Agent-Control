"""Tests for observability API endpoints."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from agent_control_models import (
    BatchEventsRequest,
    ControlExecutionEvent,
    EventQueryRequest,
)
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text

from agent_control_server.auth_framework import Operation, Principal, set_authorizer
from agent_control_server.main import app
from agent_control_server.models import DEFAULT_NAMESPACE_KEY
from agent_control_server.observability.ingest.base import IngestResult


def create_test_event(
    control_id: int = 1,
    agent_name: str | UUID | None = None,
    action: str = "observe",
    matched: bool = False,
    timestamp: datetime | None = None,
    execution_duration_ms: float | None = None,
) -> ControlExecutionEvent:
    """Create a test control execution event."""
    return ControlExecutionEvent(
        trace_id="a" * 32,  # 128-bit hex (32 chars)
        span_id="b" * 16,  # 64-bit hex (16 chars)
        agent_name=agent_name or f"agent-{uuid4().hex[:12]}",
        control_id=control_id,
        control_name=f"control-{control_id}",
        check_stage="pre",
        applies_to="llm_call",
        action=action,
        matched=matched,
        confidence=0.95,
        timestamp=timestamp or datetime.now(UTC),
        execution_duration_ms=execution_duration_ms,
    )


class _RecordingAuthorizer:
    """Test authorizer that records the operation requested by a route."""

    def __init__(self) -> None:
        self.calls: list[tuple[Operation, dict[str, Any] | None]] = []

    async def authorize(
        self,
        request: Request,
        operation: Operation,
        context: dict[str, Any] | None = None,
    ) -> Principal:
        del request
        self.calls.append((operation, context))
        return Principal(namespace_key="default")


class _NamespaceAuthorizer:
    def __init__(self, namespace_key: str) -> None:
        self.namespace_key = namespace_key

    async def authorize(
        self,
        request: Request,
        operation: Operation,
        context: dict[str, Any] | None = None,
    ) -> Principal:
        del request, operation, context
        return Principal(namespace_key=self.namespace_key)


class TestObservabilityAuthFramework:
    """Tests observability routes declare operation-based authorization."""

    def test_status_uses_read_operation(self, app: object) -> None:
        """Given a custom authorizer, when getting status, then read is authorized."""
        # Given:
        authorizer = _RecordingAuthorizer()
        set_authorizer(authorizer)
        client = TestClient(app, raise_server_exceptions=True)

        # When:
        response = client.get("/api/v1/observability/status")

        # Then:
        assert response.status_code == 200
        assert authorizer.calls == [(Operation.OBSERVABILITY_READ, None)]

    def test_ingest_events_uses_write_operation(
        self,
        app: object,
        setup_observability: object,
    ) -> None:
        """Given a custom authorizer, when ingesting events, then write is authorized."""
        # Given:
        _ = setup_observability
        authorizer = _RecordingAuthorizer()
        set_authorizer(authorizer)
        client = TestClient(app, raise_server_exceptions=True)
        request = BatchEventsRequest(events=[create_test_event()])

        # When:
        response = client.post(
            "/api/v1/observability/events",
            json=request.model_dump(mode="json"),
        )

        # Then:
        assert response.status_code == 202
        assert authorizer.calls == [(Operation.OBSERVABILITY_WRITE, None)]

    def test_events_are_scoped_to_authorized_namespace(
        self,
        app: object,
        setup_observability: object,
    ) -> None:
        _ = setup_observability
        client = TestClient(app, raise_server_exceptions=True)
        agent_name = f"agent-{uuid4().hex[:12]}"
        request = BatchEventsRequest(events=[create_test_event(agent_name=agent_name)])

        set_authorizer(_NamespaceAuthorizer("tenant-a"))
        ingest = client.post(
            "/api/v1/observability/events",
            json=request.model_dump(mode="json"),
        )
        assert ingest.status_code == 202

        query = EventQueryRequest(agent_name=agent_name, limit=10, offset=0)
        set_authorizer(_NamespaceAuthorizer("tenant-b"))
        tenant_b = client.post(
            "/api/v1/observability/events/query",
            json=query.model_dump(mode="json"),
        )
        assert tenant_b.status_code == 200
        assert tenant_b.json()["total"] == 0

        set_authorizer(_NamespaceAuthorizer("tenant-a"))
        tenant_a = client.post(
            "/api/v1/observability/events/query",
            json=query.model_dump(mode="json"),
        )
        assert tenant_a.status_code == 200
        assert tenant_a.json()["total"] == 1


class TestEventIngestion:
    """Tests for POST /events endpoint."""

    def test_ingest_events_success(self, client: TestClient, setup_observability):
        """Test successful event ingestion."""
        events = [create_test_event(i) for i in range(3)]
        request = BatchEventsRequest(events=events)

        response = client.post(
            "/api/v1/observability/events",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 202
        data = response.json()
        assert data["received"] == 3
        assert data["enqueued"] == 3
        assert data["dropped"] == 0
        assert data["status"] == "queued"

    def test_ingest_single_event(self, client: TestClient, setup_observability):
        """Test ingestion with single event."""
        events = [create_test_event()]
        request = BatchEventsRequest(events=events)

        response = client.post(
            "/api/v1/observability/events",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 202
        data = response.json()
        assert data["received"] == 1
        assert data["enqueued"] == 1
        assert data["status"] == "queued"


class TestObservabilityStatus:
    """Tests for GET /status endpoint."""

    def test_get_status(self, client: TestClient, setup_observability):
        """Test getting observability system status."""
        response = client.get("/api/v1/observability/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ingestor_initialized"] is True
        assert data["store_initialized"] is True


class TestEventQueryRequest:
    """Tests for EventQueryRequest validation."""

    def test_query_request_defaults(self):
        """Test default values for query request."""
        request = EventQueryRequest()
        assert request.limit == 100
        assert request.offset == 0
        assert request.trace_id is None
        assert request.span_id is None

    def test_query_request_with_filters(self):
        """Test query request with various filters."""
        request = EventQueryRequest(
            trace_id="a" * 32,
            agent_name=f"agent-{uuid4().hex[:12]}",
            control_ids=[1, 2, 3],
            actions=["observe", "deny"],
            matched=True,
            check_stages=["pre", "post"],
            applies_to=["llm_call"],
            limit=50,
            offset=10,
        )
        assert request.trace_id == "a" * 32
        assert len(request.control_ids) == 3
        assert request.actions == ["observe", "deny"]
        assert request.limit == 50


class TestBatchEventsRequest:
    """Tests for BatchEventsRequest validation."""

    def test_batch_request_with_events(self):
        """Test batch request with events."""
        events = [create_test_event(i) for i in range(5)]
        request = BatchEventsRequest(events=events)
        assert len(request.events) == 5

    def test_batch_request_requires_at_least_one_event(self):
        """Test batch request requires at least one event."""
        with pytest.raises(Exception):  # pydantic ValidationError
            BatchEventsRequest(events=[])


class TestControlExecutionEvent:
    """Tests for ControlExecutionEvent model."""

    def test_event_creation(self):
        """Test creating an event with required fields."""
        event = create_test_event()
        assert event.trace_id == "a" * 32
        assert event.span_id == "b" * 16
        assert event.control_name == "control-1"
        assert event.check_stage == "pre"
        assert event.applies_to == "llm_call"

    def test_event_with_all_fields(self):
        """Test creating an event with all fields."""
        event = ControlExecutionEvent(
            trace_id="a" * 32,
            span_id="b" * 16,
            agent_name="test-agent",
            control_id=1,
            control_name="test-control",
            check_stage="post",
            applies_to="tool_call",
            action="deny",
            matched=True,
            confidence=0.99,
            timestamp=datetime.now(UTC),
            execution_duration_ms=15.5,
            evaluator_name="regex",
            selector_path="input",
            error_message=None,
            metadata={"key": "value"},
        )
        assert event.action == "deny"
        assert event.matched is True
        assert event.execution_duration_ms == 15.5

    def test_event_default_metadata(self):
        """Test that metadata defaults to empty dict."""
        event = create_test_event()
        assert event.metadata == {}


class TestPostgresEventStore:
    """Tests for PostgresEventStore operations."""

    @pytest.mark.asyncio
    async def test_store_events(self, setup_observability):
        """Test storing events in PostgreSQL."""
        store = setup_observability
        events = [create_test_event(i) for i in range(5)]

        stored = await store.store(events, namespace_key=DEFAULT_NAMESPACE_KEY)
        assert stored == 5

    @pytest.mark.asyncio
    async def test_store_deduplicates_events(self, setup_observability):
        """Test that duplicate events are not stored (ON CONFLICT DO NOTHING)."""
        store = setup_observability
        event = create_test_event()

        await store.store([event], namespace_key=DEFAULT_NAMESPACE_KEY)
        # Storing same event again should not raise, but also not duplicate
        stored = await store.store([event], namespace_key=DEFAULT_NAMESPACE_KEY)
        # ON CONFLICT DO NOTHING returns the batch size, not actual inserts
        assert stored == 1

    @pytest.mark.asyncio
    async def test_ingest_via_direct_ingestor(self, setup_observability):
        """Test ingesting events via DirectEventIngestor."""
        from agent_control_server.observability import DirectEventIngestor

        store = setup_observability
        ingestor = DirectEventIngestor(store)

        events = [create_test_event(i) for i in range(3)]
        result = await ingestor.ingest(events, namespace_key=DEFAULT_NAMESPACE_KEY)

        assert result.received == 3
        assert result.processed == 3
        assert result.dropped == 0


class TestStatsTimeseries:
    """Tests for time-series stats functionality."""

    @pytest.mark.asyncio
    async def test_stats_normalize_mixed_case_agent_name_query(
        self, client: TestClient, setup_observability
    ):
        """Mixed-case agent_name query params are normalized."""
        store = setup_observability
        normalized_name = "agent-statsnorm01"

        event = create_test_event(agent_name=normalized_name, matched=True)
        await store.store([event], namespace_key=DEFAULT_NAMESPACE_KEY)

        response = client.get(
            "/api/v1/observability/stats",
            params={"agent_name": "Agent-StatsNorm01", "time_range": "1h"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["agent_name"] == normalized_name
        assert body["totals"]["execution_count"] == 1

    @pytest.mark.asyncio
    async def test_stats_without_timeseries(self, client: TestClient, setup_observability):
        """Default response has no timeseries."""
        store = setup_observability
        agent_name = f"agent-{uuid4().hex[:12]}"

        # Create and store an event
        event = create_test_event(agent_name=agent_name, matched=True)
        await store.store([event], namespace_key=DEFAULT_NAMESPACE_KEY)

        response = client.get(
            "/api/v1/observability/stats",
            params={"agent_name": str(agent_name), "time_range": "1h"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["totals"]["timeseries"] is None
        assert data["totals"]["execution_count"] == 1

    @pytest.mark.asyncio
    async def test_stats_with_timeseries(self, client: TestClient, setup_observability):
        """With include_timeseries=true, returns buckets."""
        store = setup_observability
        agent_name = f"agent-{uuid4().hex[:12]}"
        now = datetime.now(UTC)

        # Create events spread across time
