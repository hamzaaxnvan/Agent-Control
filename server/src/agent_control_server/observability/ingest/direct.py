"""Direct event ingestor implementation.

This module provides the DirectEventIngestor, which processes events
immediately by writing them to an async control-event sink. Existing
store-based callers are preserved by wrapping EventStore instances in the
default EventStoreControlEventSink internally.

For high-throughput scenarios, users can implement their own buffered
ingestor (e.g., QueuedEventIngestor, RedisEventIngestor).
"""

import json
import logging

from agent_control_models.observability import ControlExecutionEvent
from agent_control_telemetry.sinks import AsyncControlEventSink

from ..sinks import EventStoreControlEventSink
from ..store.base import EventStore
from .base import EventIngestor, IngestResult

logger = logging.getLogger(__name__)


class DirectEventIngestor(EventIngestor):
    """Processes events immediately by writing them to an async control-event sink.

    This is the simplest ingestor implementation. Events are written
    directly to the configured sink, adding ~5-20ms latency per batch.

    For use cases that require lower latency or higher throughput,
    implement a custom buffered ingestor (e.g., QueuedEventIngestor).

    Attributes:
        sink: The AsyncControlEventSink used to write events
        log_to_stdout: Whether to log events as structured JSON
    """

    def __init__(
        self,
        store: EventStore | AsyncControlEventSink | EventStoreControlEventSink,
        log_to_stdout: bool = False,
    ):
        """Initialize the ingestor.
