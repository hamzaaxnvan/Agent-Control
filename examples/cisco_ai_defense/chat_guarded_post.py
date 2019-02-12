"""Decorator-based example focusing on POST (output) checks.

Prereqs:
  1) Run the server with Cisco AI Defense evaluator available
  2) Seed controls and attach to the agent with examples/cisco_ai_defense/setup_ai_defense_controls.py
  3) Set env: AGENT_CONTROL_URL, AGENT_CONTROL_API_KEY

Run:
  uv run chat_guarded_post.py --agent-name ai-defense-demo

This example sends a safe input but produces a toxic/unsafe output to
demonstrate that POST-stage checks (output) will block the response.
"""

from __future__ import annotations

import argparse
import asyncio
import os

import agent_control
import httpx
from agent_control import control


@control()
async def reply_with_potentially_unsafe_output(message: str) -> str:
