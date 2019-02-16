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
