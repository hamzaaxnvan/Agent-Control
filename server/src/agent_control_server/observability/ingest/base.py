"""Base interfaces for event ingestion.

This module defines the EventIngestor protocol that all event ingestors
must implement. The protocol is simple enough that users can easily
create custom implementations (e.g., QueuedEventIngestor, RedisEventIngestor).
"""

from typing import Protocol, runtime_checkable

from agent_control_models.observability import ControlExecutionEvent
from pydantic import BaseModel, Field


class IngestResult(BaseModel):
    """Result of an event ingestion operation.

    Attributes:
        received: Number of events received
        processed: Number of events successfully processed
        dropped: Number of events dropped (e.g., due to errors)
    """

