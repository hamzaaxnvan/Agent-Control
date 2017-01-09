"""Register an agent by name.

This helper simplifies onboarding by registering the agent with the running
server using its name. Agents are keyed by `agent_name`.

Env required:
- AGENT_CONTROL_URL (e.g., http://localhost:8000)
- AGENT_CONTROL_API_KEY (X-API-Key for the server)

Usage:
  uv run register_agent.py [--agent-name ai-defense-demo]
"""

from __future__ import annotations

import argparse
import os

import agent_control
import httpx



def main() -> int:
    parser = argparse.ArgumentParser(description="Register agent and persist a stable agent ID")
    parser.add_argument("--agent-name", default="ai-defense-demo", help="Agent name")
