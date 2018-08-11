#!/usr/bin/env python3
"""Demo agent: target context fixed at SDK init().

Walks through every touchpoint of the V1 contract:

1. ``init(target_type=..., target_id=...)`` returns the merged effective
   set (direct attachments + policy-derived + target bindings).
2. ``@control()`` decorator runs automatically against that merged set.
3. ``evaluate_controls(...)`` defaults its target context from the
   session, so callers don't need to repeat themselves.
4. A per-call target that disagrees with the session target is rejected
   with a clear ``ValueError``: the SDK supports one target per session.

Prerequisites:
    - Agent Control server running.
    - ``setup_controls.py`` executed first to provision the agent + bindings.

Usage:
    uv run python examples/target_context_demo/demo_agent.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Add the SDK to path for development.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../sdks/python/src"))

import agent_control
from agent_control import ControlViolationError, control

AGENT_NAME = "demo-target-bot"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


def simulate_llm_response(prompt: str) -> str:
    """Stand-in for an LLM. Crafts an output that triggers the PII control
    when the prompt asks about a customer record."""
    if "customer record" in prompt.lower():
        return "Customer 123-45-6789 paid invoice INV-001."
    return f"You said: {prompt}"


@control()
async def chat(message: str) -> str:
    return simulate_llm_response(message)


def show_effective_controls(label: str) -> None:
    controls = agent_control.get_server_controls() or []
    names = [c["name"] for c in controls]
