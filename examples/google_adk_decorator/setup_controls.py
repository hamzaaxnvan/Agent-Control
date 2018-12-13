#!/usr/bin/env python3
"""Create controls for the Google ADK decorator example."""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import httpx
from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "google-adk-decorator"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


def _control_specs(execution: str) -> list[tuple[str, dict[str, Any]]]:
    """Build control definitions for the requested execution mode."""
    return [
        (
            "adk-decorator-block-restricted-cities",
            {
                "description": "Block requests for restricted cities before tool execution",
                "enabled": True,
                "execution": execution,
                "scope": {
                    "step_types": ["tool"],
                    "step_names": ["get_current_time", "get_weather"],
                    "stages": ["pre"],
                },
                "condition": {
                    "selector": {"path": "input.city"},
                    "evaluator": {
                        "name": "list",
                        "config": {
                            "values": ["Pyongyang", "Tehran", "Damascus"],
                            "logic": "any",
                            "match_on": "match",
                            "match_mode": "exact",
                            "case_sensitive": False,
                        },
                    },
                },
                "action": {"decision": "deny"},
            },
        ),
        (
            "adk-decorator-block-internal-contact-output",
            {
                "description": "Block internal contact details in decorated tool output",
                "enabled": True,
                "execution": execution,
                "scope": {
                    "step_types": ["tool"],
                    "step_names": ["get_current_time", "get_weather"],
                    "stages": ["post"],
                },
                "condition": {
                    "selector": {"path": "output.note"},
                    "evaluator": {
                        "name": "regex",
                        "config": {
                            "pattern": r"support@internal\.example|123-45-6789",
                        },
                    },
                },
                "action": {"decision": "deny"},
            },
        ),
    ]


async def _ensure_control(
    client: AgentControlClient,
    name: str,
    data: dict[str, Any],
) -> int:
    """Create the control or update the existing definition."""
    try:
        result = await controls.create_control(client, name=name, data=data)
