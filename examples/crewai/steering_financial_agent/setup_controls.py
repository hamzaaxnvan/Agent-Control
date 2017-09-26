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
                                    "crimea",
                                ],
                                "logic": "any",
                                "match_mode": "contains",
                                "case_sensitive": False,
                            },
                        },
                    },
                    "action": {"decision": "deny"},
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  DENY: Fraud Score Too High                            │
            # │  Uses JSON evaluator with field constraints.           │
            # │  Blocks when fraud_score exceeds 0.8 threshold.        │
            # └─────────────────────────────────────────────────────────┘
            (
                "deny-high-fraud-score",
                {
                    "description": "Block transactions with fraud score above 0.8",
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["process_transfer"],
                        "stages": ["pre"],
                    },
                    "condition": {
                        "selector": {"path": "input"},
                        "evaluator": {
                            "name": "json",
                            "config": {
                                "field_constraints": {
                                    "fraud_score": {"type": "number", "max": 0.8}
                                }
                            },
                        },
                    },
                    "action": {"decision": "deny"},
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  STEER: Large Transfer → Require 2FA                   │
            # │  Uses JSON evaluator with oneOf schema.                │
            # │  Either amount < $10k OR amount >= $10k with 2FA.      │
            # │  Provides steering_context so agent knows what to do.  │
            # └─────────────────────────────────────────────────────────┘
            (
                "steer-require-2fa",
                {
                    "description": "Require 2FA verification for transfers >= $10,000",
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["process_transfer"],
                        "stages": ["pre"],
                    },
                    "condition": {
                        "selector": {"path": "input"},
                        "evaluator": {
                            "name": "json",
                            "config": {
                                "json_schema": {
                                    "type": "object",
                                    "oneOf": [
                                        {
                                            "properties": {
                                                "amount": {
                                                    "type": "number",
