"""Google ADK example using Agent Control callbacks."""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

import agent_control
from agent_control import AgentControlClient, ControlSteerError, ControlViolationError
from agent_control.evaluation import check_evaluation
from agent_control_models import Step
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

load_dotenv()

AGENT_NAME = "google-adk-callbacks"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
MODEL_NAME = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

CITY_DATA = {
    "new york": {
        "display_name": "New York",
        "local_time": "10:30 AM",
        "weather": "Sunny, 72 F",
    },
    "london": {
        "display_name": "London",
        "local_time": "3:30 PM",
        "weather": "Cloudy, 61 F",
    },
    "tokyo": {
        "display_name": "Tokyo",
        "local_time": "11:30 PM",
        "weather": "Clear, 68 F",
    },
    "testville": {
        "display_name": "Testville",
        "local_time": "9:00 AM",
        "weather": "Mild, 65 F",
    },
}


def _tool_input_schema() -> dict[str, Any]:
    return {"city": {"type": "string"}}


def _tool_output_schema() -> dict[str, Any]:
    return {
        "city": {"type": "string"},
        "value": {"type": "string"},
        "note": {"type": "string"},
    }


agent_control.init(
    agent_name=AGENT_NAME,
    agent_description="Google ADK example using Agent Control callbacks",
    server_url=SERVER_URL,
    steps=[
        {
            "type": "llm",
            "name": "root_agent",
            "description": "Primary Google ADK model call",
            "input_schema": {"text": {"type": "string"}},
            "output_schema": {"text": {"type": "string"}},
        },
        {
            "type": "tool",
            "name": "get_current_time",
            "description": "Get the current time for a city.",
            "input_schema": _tool_input_schema(),
            "output_schema": _tool_output_schema(),
        },
        {
            "type": "tool",
            "name": "get_weather",
            "description": "Get the weather for a city.",
            "input_schema": _tool_input_schema(),
            "output_schema": _tool_output_schema(),
        },
    ],
)


_RUN_SYNC_TIMEOUT = 30  # seconds


def _run_sync(coro: Any) -> Any:
    """Run async evaluation safely from sync ADK callbacks.

    ADK callbacks are synchronous, but the Agent Control SDK is async.
    When no event loop is running we can use ``asyncio.run`` directly.
    Otherwise we spawn a short-lived daemon thread with its own loop so
    that we never nest ``run`` calls inside an existing loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            result_box["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            result_box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=_RUN_SYNC_TIMEOUT)

    if thread.is_alive():
