"""Emit observability events for evaluations made over plain HTTP.

``POST /api/v1/evaluation`` is deliberately evaluation-only: it returns the
decision and writes no observability events. The SDK is what normally
reconstructs and sends them, so an application that calls the endpoint
directly shows nothing in Agent Control's Monitor tab.

These two web demos call the endpoint directly, because they need the full
response to show per-control detail. So they reconstruct the events the same
way the SDK does and queue them through the SDK's batcher.

Set AGENT_CONTROL_OBSERVE=0 to turn this off.
"""

from __future__ import annotations

import os
from typing import Any

import agent_control
from agent_control.evaluation_events import (
    build_control_execution_events,
    enqueue_observability_events,
)
from agent_control_models.controls import ControlDefinition
from agent_control_models.evaluation import EvaluationRequest, EvaluationResponse

ENABLED = os.getenv("AGENT_CONTROL_OBSERVE", "1") != "0"

_started = False


def start(agent_name: str, server_url: str, step_name: str, tool_name: str) -> bool:
    """Initialize the SDK so its observability batcher is running.

    Both steps are declared here. init() replaces the agent's step list, so
    leaving the tool step out would deregister it and the tool-stage control
    would have nothing to attach to.

    Args:
        agent_name: The agent to register.
        server_url: The Agent Control server.
        step_name: The chat step's name.
        tool_name: The lookup tool's step name.

    Returns:
        True when observability is on and initialization succeeded.
    """
    global _started
    if not ENABLED or _started:
        return _started
    try:
        agent_control.init(
            agent_name=agent_name,
            agent_description="TypeSafe Jev demo",
            server_url=server_url,
            steps=[
                {"type": "llm", "name": step_name, "description": "A chat turn."},
                {
                    "type": "tool",
                    "name": tool_name,
