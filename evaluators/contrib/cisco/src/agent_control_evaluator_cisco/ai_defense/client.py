from __future__ import annotations

# Thin REST client for Cisco AI Defense Chat Inspection.
# Uses httpx.AsyncClient and the OpenAPI-defined endpoint/header.
from dataclasses import dataclass, field
from typing import Any

try:
    import httpx

    AI_DEFENSE_HTTPX_AVAILABLE = True
except ImportError:  # Narrow to import error only
    httpx = None  # type: ignore
    AI_DEFENSE_HTTPX_AVAILABLE = False


# Regions from ai_defense_api.json "servers" section
REGION_BASE_URLS: dict[str, str] = {
    "us": "https://us.api.inspect.aidefense.security.cisco.com",
    "ap": "https://ap.api.inspect.aidefense.security.cisco.com",
    "eu": "https://eu.api.inspect.aidefense.security.cisco.com",
}


def build_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/api/v1/inspect/chat"


@dataclass
class AIDefenseClient:
    """Minimal async client for Cisco AI Defense Chat Inspection.

    Attributes:
        api_key: API key used for authentication header
        endpoint_url: Full URL to POST /api/v1/inspect/chat
        timeout_s: Timeout in seconds
    """

    api_key: str = field(repr=False)
    endpoint_url: str
    timeout_s: float

    _client: httpx.AsyncClient | None = field(  # type: ignore[name-defined]
        default=None,
        repr=False,
        compare=False,
    )

    async def _get_client(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
