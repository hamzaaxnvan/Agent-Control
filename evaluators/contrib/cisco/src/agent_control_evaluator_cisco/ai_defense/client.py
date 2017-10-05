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
