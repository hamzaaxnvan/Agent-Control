#!/usr/bin/env python3
"""Create controls for the direct Galileo Luna evaluator demo.

Prerequisites:
    - Agent Control server running at AGENT_CONTROL_URL, default http://localhost:8000
    - Galileo credentials set where demo_agent.py will run:
      GALILEO_API_SECRET_KEY or GALILEO_API_SECRET
      GALILEO_LUNA_INVOKE_URL
      GALILEO_LUNA_SCORER_ID (required)

Usage:
    uv run python setup_controls.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "galileo-luna-agent"
AGENT_DESCRIPTION = "Demo agent protected by direct Galileo Luna scorer controls"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

LUNA_SCORER_ID = os.getenv("GALILEO_LUNA_SCORER_ID")
LUNA_SCORER_LABEL = os.getenv("GALILEO_LUNA_SCORER_LABEL")
# Deprecated compatibility ID; Orbit invokes the scorer's current default version.
LUNA_SCORER_VERSION_ID = os.getenv("GALILEO_LUNA_SCORER_VERSION_ID")
LUNA_THRESHOLD = float(os.getenv("GALILEO_LUNA_THRESHOLD", "0.5"))
LUNA_PAYLOAD_FIELD = os.getenv("GALILEO_LUNA_PAYLOAD_FIELD", "output")

if not LUNA_SCORER_ID:
    raise ValueError("GALILEO_LUNA_SCORER_ID is required.")
if LUNA_PAYLOAD_FIELD not in {"input", "output"}:
    raise ValueError("GALILEO_LUNA_PAYLOAD_FIELD must be either 'input' or 'output'.")

DEMO_STEPS = [
    {
        "type": "llm",
        "name": "draft_customer_reply",
        "description": "Draft customer-facing support replies.",
        "input_schema": {"message": {"type": "string"}},
        "output_schema": {"reply": {"type": "string"}},
    }
]


def luna_config() -> dict[str, Any]:
    """Build the direct Luna evaluator config used by the composite control."""
    config: dict[str, Any] = {
        "scorer_id": LUNA_SCORER_ID,
        "threshold": LUNA_THRESHOLD,
        "operator": "gte",
        "payload_field": LUNA_PAYLOAD_FIELD,
    }
    if LUNA_SCORER_LABEL:
        config["scorer_label"] = LUNA_SCORER_LABEL
    if LUNA_SCORER_VERSION_ID:
        config["scorer_version_id"] = LUNA_SCORER_VERSION_ID
    return config


DEMO_CONTROLS: list[dict[str, Any]] = [
    {
        "name": "luna-toxic-escalation-output",
        "definition": {
            "description": (
                "For risky customer messages, score the drafted reply with direct "
                "Galileo Luna and block when the local threshold matches."
            ),
            "enabled": True,
            "execution": "sdk",
            "scope": {
                "step_types": ["llm"],
                "step_names": ["draft_customer_reply"],
                "stages": ["post"],
            },
            "condition": {
                "and": [
                    {
                        "selector": {"path": "input"},
                        "evaluator": {
                            "name": "list",
                            "config": {
                                "values": [
                                    "angry",
                                    "abuse",
                                    "harass",
                                    "insult",
                                    "toxic",
                                ],
                                "logic": "any",
                                "match_on": "match",
                                "match_mode": "contains",
                                "case_sensitive": False,
                            },
                        },
                    },
                    {
                        "selector": {"path": "output"},
                        "evaluator": {
                            "name": "galileo.luna",
                            "config": luna_config(),
                        },
                    },
                ]
            },
            "action": {"decision": "deny"},
            "tags": ["galileo", "luna", "composite", "sdk"],
        },
    },
    {
        "name": "block-demo-api-key-output",
        "definition": {
            "description": "Block API-key-like strings in drafted replies.",
            "enabled": True,
            "execution": "sdk",
            "scope": {
                "step_types": ["llm"],
                "step_names": ["draft_customer_reply"],
                "stages": ["post"],
            },
            "condition": {
                "selector": {"path": "output"},
                "evaluator": {
                    "name": "regex",
                    "config": {"pattern": r"\bsk-[A-Za-z0-9_-]{12,}\b"},
                },
            },
            "action": {"decision": "deny"},
            "tags": ["regex", "secret", "sdk"],
        },
    },
]


async def create_or_get_control(
    client: AgentControlClient,
    *,
