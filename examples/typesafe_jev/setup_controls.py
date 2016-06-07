#!/usr/bin/env python3
"""Create the TypeSafe Jev demo controls on an Agent Control server.

The controls live on the server, not in this file's process. Once created they
are visible and editable in the Agent Control UI, and any client that evaluates
against this agent uses them.

Prerequisites:
    - An Agent Control server at AGENT_CONTROL_URL, default http://localhost:8000
    - This example installed into that server's environment, because these
      controls run with execution "server" and the server is what loads
      the evaluator.
    - TYPESAFE_API_KEY set in the server's environment, not here.

Usage:
    python setup_controls.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "typesafe-jev-demo"
AGENT_DESCRIPTION = "Demo agent screened by TypeSafe Jev controls"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
STEP_NAME = "chat"
TOOL_NAME = "lookup_customers"

DEMO_STEPS: list[dict[str, Any]] = [
    {
        "type": "llm",
        "name": STEP_NAME,
        "description": "A chat turn screened before the model runs.",
        "input_schema": {"message": {"type": "string"}},
        "output_schema": {"reply": {"type": "string"}},
    },
    # The assistant's one tool. Registering it as its own step is what lets a
    # control screen the call the model wants to make, before it runs.
    {
        "type": "tool",
        "name": TOOL_NAME,
        "description": "Read customer records from the bank's customer database.",
        "input_schema": {
            "fields": {"type": "array"},
            "name": {"type": "string"},
            "region": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "output_schema": {"rows": {"type": "array"}},
    },
]


# --- question builders ------------------------------------------------------
#
# Jev has three primitives, and each one suits a different shape of question.
#
#   noul    "is this statement true?"   -> a probability, 0 to 1
#   score   "rate this on a rubric"     -> an ordinal, 0 to len(levels) - 1
#   choice  "which one of these?"       -> exactly one option name
#
# A question with a threshold decides: it is an input to decide.combine.
# One without a threshold is asked and recorded only, so it cannot fire the
# control and cannot stop it firing.


def noul(
    *,
    instructions: str,
    when_true: str,
    when_false: str,
    threshold: float | None = None,
) -> dict[str, Any]:
    """A yes/no question returning the probability that it is true.

    Args:
        instructions: The question to ask.
        when_true: What a "yes" means. This is guidance for the model, not a label.
        when_false: What a "no" means.
        threshold: Fire at or above this probability. Omit to record only.
    """
    question: dict[str, Any] = {
        "type": "noul",
        "instructions": instructions,
        "criteria": {"true": when_true, "false": when_false},
    }
    if threshold is not None:
        question["threshold"] = threshold
    return question


def score(
    *,
    instructions: str,
    levels: list[str],
    threshold: float | None = None,
