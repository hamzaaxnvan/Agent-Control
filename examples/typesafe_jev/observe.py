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
