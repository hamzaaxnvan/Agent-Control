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
