"""Google ADK example using the packaged Agent Control plugin."""

from __future__ import annotations

import os

import agent_control
from agent_control.integrations.google_adk import AgentControlPlugin
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.apps import App

load_dotenv()

AGENT_NAME = "google-adk-plugin"
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
