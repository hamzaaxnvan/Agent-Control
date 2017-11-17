"""Thin async REST client for the TypeSafe System One endpoint."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any

# Statuses worth retrying: the service is busy or briefly unavailable, not
# wrong. 529 is the overloaded response the API returns under load.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 0.4

try:
    import httpx

    TYPESAFE_HTTPX_AVAILABLE = True
except ImportError:  # Narrow to import error only
    httpx = None  # type: ignore[assignment]
    TYPESAFE_HTTPX_AVAILABLE = False


def build_endpoint(base_url: str) -> str:
    """Return the System One URL for an API origin."""
    return f"{base_url.rstrip('/')}/v1/systemone"


@dataclass
class TypeSafeClient:
    """Minimal async client for POST /v1/systemone.

    Attributes:
        api_key: Bearer token for the Authorization header.
        endpoint_url: Full URL to POST.
        timeout_s: Request timeout in seconds.
    """

    api_key: str = field(repr=False)
    endpoint_url: str
    #: Total budget for one system_one call, retries included. The engine wraps
    #: the evaluator in a timeout of its own, so retrying past this only turns a
