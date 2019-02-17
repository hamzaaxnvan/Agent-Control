"""A guarded bank assistant, to show what the controls feel like in a product.

The score inspector in app.py shows what the guardrails think. This shows what
the user experiences: a chat window where some turns answer normally, some are
refused before the model is ever called, some are steered, some have a tool
call stopped, and some have the model's reply withheld.

A guarded turn screens up to four things:

    1. the user's message, at the pre stage on the chat step
    2. every tool call the model asks for, at the pre stage on the tool step
    3. nothing, if a deny already stopped the turn
    4. the model's reply, at the post stage, withheld on a deny

The turn is streamed to the page as newline-delimited JSON, one event per
step. That is not decoration: the guardrail calls take a few hundred
milliseconds each and the model takes seconds, so a single spinner makes the
controls look like the slow part when they are not.

Standard library only.

Prerequisites:
    - An Agent Control server at AGENT_CONTROL_URL, default http://localhost:8000
    - This example installed into that server's environment, so the
      evaluator is discovered through its entry point
    - python setup_controls.py has been run
    - Optionally OPENAI_API_KEY or ANTHROPIC_API_KEY, otherwise a scripted
      offline model is used

Run:
    python chat_app.py
    open http://localhost:8500
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import customers
import env_file
import llm
import observe

env_file.load()

HERE = Path(__file__).parent
PORT = int(os.getenv("CHAT_PORT", "8500"))
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000").rstrip("/")
AGENT_NAME = os.getenv("AGENT_NAME", "typesafe-jev-demo")
STEP_NAME = os.getenv("STEP_NAME", "chat")
TOOL_NAME = os.getenv("TOOL_NAME", "lookup_customers")
#: How many times the model may call a tool before the app gives up.
MAX_TOOL_STEPS = 3
#: How many returned rows the page shows before it says "and N more".
TRACE_ROW_LIMIT = 3

WITHHELD = (
    "I generated a reply, but a guardrail withheld it before it reached you. "
    "Please rephrase, or contact support if you need this information."
)

# Steering context is written for the model, not the person. When the model
# platform refuses outright there is no reply to steer, so the application
# needs its own user-facing fallback.
STEER_FALLBACK = (
    "I'm not able to advise on that one. I can put you in touch with a licensed "
    "advisor, or help with something else."
)


def _agent_controls() -> Any:
    """Fetch the agent's controls, used to stamp identity onto events."""
    request = urllib.request.Request(
        f"{SERVER_URL}/api/v1/agents/{AGENT_NAME}/controls",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _evaluate(stage: str, step: dict[str, Any]) -> dict[str, Any]:
    """Screen one step at one stage through the Agent Control server.

    The endpoint writes no observability events, so the reconstructed events
    are queued separately. Without this the Monitor tab stays empty.
    """
    payload = {"agent_name": AGENT_NAME, "stage": stage, "step": step}
    request = urllib.request.Request(
        f"{SERVER_URL}/api/v1/evaluation",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
