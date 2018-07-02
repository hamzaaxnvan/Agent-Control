"""
Cisco AI Defense Chat Inspection Demo

This script calls Cisco AI Defense Chat Inspection directly and blocks when
InspectResponse.is_safe is False. It demonstrates evaluating both user
prompts (pre) and model responses (post) without Agent Control server policies.

Env vars:
    AI_DEFENSE_API_KEY   - required, used as X-Cisco-AI-Defense-API-Key
    AI_DEFENSE_API_URL   - optional, defaults to the public Inspect endpoint
    AI_DEFENSE_TIMEOUT_S - optional, request timeout seconds (int/float)

Run:
    uv run chat_inspect_demo.py [--debug]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

DEFAULT_INSPECT_URL = (
    "https://us.api.inspect.aidefense.security.cisco.com/api/v1/inspect/chat"
)


def _mask(s: str, keep: int = 6) -> str:
    if not s:
        return ""
    if len(s) <= keep:
        return "***"
    return f"{s[:keep]}...{s[-4:]}"


def build_request_payload(
    prompt: str | None = None,
    response: str | None = None,
    history: list[tuple[Literal["user", "assistant"], str]] | None = None,
) -> dict[str, Any]:
    """Build a simple chat-style payload.

    Many Chat Inspection APIs accept a messages array. Adjust as needed if your
    deployment expects additional fields (model, metadata, etc.).
    """
    messages: list[dict[str, str]] = []
    if history:
        for role, content in history:
            messages.append({"role": role, "content": content})
    if prompt:
        messages.append({"role": "user", "content": prompt})
    if response:
        messages.append({"role": "assistant", "content": response})
    return {"messages": messages}


@dataclass
class InspectOutcome:
    is_safe: bool | None
    duration_ms: float
    raw: dict[str, Any] | None
    error: str | None = None


class ChatInspectClient:
    """Standalone direct-HTTP client used by the demo.

    This example intentionally avoids importing the contrib evaluator package so
    the direct API demo can run with only the example environment dependencies.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
