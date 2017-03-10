"""
Setup script for the CrewAI Financial Agent steering example.

Creates controls that demonstrate the three supported action types:
- DENY:  Hard-block sanctioned countries and fraud (no recovery)
- STEER: Guide the agent through 2FA and manager approval workflows
- OBSERVE: Flag new recipients and unusual hours for audit (no blocking)

Run once before running the agent:
    uv run --active python setup_controls.py
"""

import asyncio
import os

from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "crewai-financial-agent"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


async def setup():
    async with AgentControlClient(base_url=SERVER_URL) as client:
        # ── Register Agent ──────────────────────────────────────────────
        agent = Agent(
            agent_name=AGENT_NAME,
            agent_description=(
                "CrewAI financial services agent that processes wire transfers "
                "with compliance, fraud, and approval controls"
            ),
        )

        try:
            await agents.register_agent(client, agent, steps=[])
            print(f"  Agent registered: {AGENT_NAME}")
        except Exception as e:
            if "already exists" in str(e).lower() or "409" in str(e):
                print(f"  Agent already registered: {AGENT_NAME}")
            else:
                raise

        # ── Control Definitions ─────────────────────────────────────────
        control_defs = [
            # ┌─────────────────────────────────────────────────────────┐
            # │  DENY: Sanctioned Countries                            │
            # │  Uses LIST evaluator with contains matching.           │
            # │  Blocks transfers to OFAC-sanctioned destinations.     │
            # └─────────────────────────────────────────────────────────┘
            (
                "deny-sanctioned-countries",
                {
                    "description": "Block transfers to OFAC-sanctioned countries",
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["process_transfer"],
                        "stages": ["pre"],
                    },
                    "condition": {
                        "selector": {"path": "input.destination_country"},
                        "evaluator": {
                            "name": "list",
                            "config": {
                                "values": [
                                    "north korea",
                                    "iran",
                                    "syria",
                                    "cuba",
