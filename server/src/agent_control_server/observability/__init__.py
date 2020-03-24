"""Observability package for control execution tracking.

This package provides a simplified, interface-based design for observability:

- **EventIngestor**: Entry point for events (direct or custom buffered processing)
- **EventStore**: Storage backend (Postgres or custom)

The architecture is designed for flexibility:
- Swap implementations via dependency injection
- No pre-aggregation - stats computed at query time
- Simple enough for open-source adoption
- Extensible for enterprise use cases

Example:
    from agent_control_server.observability import (
        DirectEventIngestor,
        PostgresEventStore,
    )

    # Default setup
