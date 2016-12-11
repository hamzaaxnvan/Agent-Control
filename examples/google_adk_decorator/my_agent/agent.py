"""Google ADK example using Agent Control's @control() decorator."""

from __future__ import annotations

import os

import agent_control
from agent_control import ControlSteerError, ControlViolationError, control
from dotenv import load_dotenv
from google.adk.agents import LlmAgent

load_dotenv()

AGENT_NAME = "google-adk-decorator"
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


def _city_record(city: str) -> dict[str, str]:
    """Get deterministic city data for the example tools."""
    return CITY_DATA.get(
        city.lower(),
        {
            "display_name": city.title() or "Unknown City",
            "local_time": "Unknown",
            "weather": "Unavailable",
        },
    )


def _note_for_city(city: str) -> str:
    """Return a deterministic note used by the post-tool demo control."""
    if city.lower() == "testville":
        return "Internal escalation contact: support@internal.example"
    return "Public city information only."


def _mark_tool(step_name: str):
    """Mark a function as a tool before @control() inspects it."""
    def decorator(func):
        func.name = step_name  # type: ignore[attr-defined]
        func.tool_name = step_name  # type: ignore[attr-defined]
        return func
    return decorator


@control(step_name="get_current_time")
