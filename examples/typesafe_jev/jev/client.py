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
    #: recoverable error into a timeout.
    timeout_s: float
    max_attempts: int = MAX_ATTEMPTS

    _client: httpx.AsyncClient | None = field(  # type: ignore[name-defined]
        default=None,
        repr=False,
        compare=False,
    )

    async def _get_client(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
        if not TYPESAFE_HTTPX_AVAILABLE:  # pragma: no cover
            raise RuntimeError("httpx not installed; cannot call the TypeSafe API")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def system_one(
        self,
        state: Any,
        questions: dict[str, dict[str, Any]],
        model: str,
    ) -> dict[str, Any]:
        """Ask one batch of typed questions about a state.

        Args:
            state: The context Jev evaluates. A string, mapping, or sequence.
            questions: Question objects keyed by question id.
            model: Model identifier.

        Returns:
            The decoded JSON response body.

        Raises:
            RuntimeError: The response body is not a JSON object.
            httpx.HTTPStatusError: The API returned a non-2xx status.
        """
        client = await self._get_client()
        payload: dict[str, Any] = {"model": model, "state": state, "questions": questions}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        deadline = time.monotonic() + self.timeout_s
