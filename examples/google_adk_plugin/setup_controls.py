#!/usr/bin/env python3
"""Create controls for the Google ADK packaged-plugin example."""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import httpx
from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "google-adk-plugin"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
TOOL_STEP_NAMES = [
    "root_agent.get_current_time",
    "root_agent.get_weather",
]


def _control_specs(execution: str) -> list[tuple[str, dict[str, Any]]]:
    """Build control definitions for the requested execution mode."""
    return [
        (
            "adk-plugin-block-prompt-injection",
            {
                "description": "Block prompt injection patterns before the ADK model call",
                "enabled": True,
                "execution": execution,
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
            },
        ),
        (
            "adk-plugin-block-restricted-cities",
            {
                "description": "Block requests for restricted cities before tool execution",
                "enabled": True,
                "execution": execution,
                "scope": {
                    "step_types": ["tool"],
                    "step_names": TOOL_STEP_NAMES,
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
            "adk-plugin-block-internal-contact-output",
            {
                "description": "Block internal contact details in tool output",
                "enabled": True,
                "execution": execution,
                "scope": {
