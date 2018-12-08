"""Web playground for TypeSafe Jev controls, served from an Agent Control server.

This is a thin client. It holds no controls and runs no engine. Each message is
POSTed to the server's /api/v1/evaluation endpoint, which loads the agent's
controls from its database and runs them. Edit a control in the Agent Control
UI and the next check here reflects it.

Standard library only.

Prerequisites:
    - An Agent Control server at AGENT_CONTROL_URL, default http://localhost:8000
    - This example installed into that server's environment, so the
      evaluator is discovered through its entry point
    - TYPESAFE_API_KEY set in the server's environment, not here
    - python setup_controls.py has been run

Run:
    python app.py
    open http://localhost:8400
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import env_file
import observe

env_file.load()

HERE = Path(__file__).parent
PORT = int(os.getenv("PORT", "8400"))
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000").rstrip("/")
AGENT_NAME = os.getenv("AGENT_NAME", "typesafe-jev-demo")
STEP_NAME = os.getenv("STEP_NAME", "chat")
TOOL_NAME = os.getenv("TOOL_NAME", "lookup_customers")


def _post(path: str, payload: dict[str, Any], timeout: float = 120.0) -> Any:
    """POST JSON to the Agent Control server and return the decoded response."""
    request = urllib.request.Request(
        f"{SERVER_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _get(path: str, timeout: float = 30.0) -> Any:
    """GET JSON from the Agent Control server."""
    request = urllib.request.Request(
        f"{SERVER_URL}{path}", headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _row(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten one ControlMatch into what the page renders.

    A control asks a battery, so one control carries several answers. The page
    shows the whole vector plus the routed outcome, the way the cookbook's
    interpret() does.
    """
    result = entry.get("result") or {}
    metadata = result.get("metadata") or {}
    usage = metadata.get("usage") or {}
    return {
        "control": entry.get("control_name"),
        "action": str(entry.get("action") or ""),
        "matched": result.get("matched"),
        "answers": metadata.get("answers") or {},
        "routed_action": metadata.get("routed_action"),
        "contributions": metadata.get("contributions") or {},
        "severity_escalated": bool(metadata.get("severity_escalated")),
        "decide_mode": metadata.get("decide_mode"),
        "decided_by": metadata.get("decided_by"),
