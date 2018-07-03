#!/usr/bin/env python3
"""Create controls for the Google ADK callbacks example."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "google-adk-callbacks"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

CONTROL_SPECS: list[tuple[str, dict[str, Any]]] = [
    (
        "adk-callbacks-block-prompt-injection",
        {
            "description": "Block prompt injection patterns before the ADK model call",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["pre"]},
            "condition": {
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": (
                            r"(?i)(ignore.{0,20}(previous|prior|above).{0,20}instructions"
                            r"|system:|forget everything|reveal secrets)"
                        )
                    },
                },
            },
            "action": {"decision": "deny"},
