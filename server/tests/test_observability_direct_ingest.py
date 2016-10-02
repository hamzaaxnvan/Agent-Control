from __future__ import annotations

import logging

import pytest
from agent_control_models.observability import ControlExecutionEvent
from agent_control_telemetry.sinks import SinkResult

from agent_control_server.models import DEFAULT_NAMESPACE_KEY
from agent_control_server.observability.ingest.direct import DirectEventIngestor
from agent_control_server.observability.store.base import EventStore


class FailingStore(EventStore):
    async def store(
        self,
        events: list[ControlExecutionEvent],
        *,
        namespace_key: str,
    ) -> int:
        raise RuntimeError("boom")

    async def query_stats(
        self,
        agent_name,
        time_range,
        *,
        control_id=None,
        include_timeseries=False,
        bucket_size=None,
        namespace_key,
    ):  # pragma: no cover - not used
        raise NotImplementedError

    async def query_events(self, query, *, namespace_key):  # pragma: no cover - not used
        raise NotImplementedError
