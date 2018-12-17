"""
Setup script for Banking Transaction Agent controls.

Demonstrates the Agent Control action types in a realistic banking scenario:
- OBSERVE: Simple transfers that trigger non-blocking audit controls
- DENY: Compliance violations (sanctioned countries, fraud)
- STEER: Large transfers requiring verification and approval

Run this once before running the autonomous agent demo.
"""

import asyncio
import os

from agent_control import Agent, AgentControlClient, agents, controls

AGENT_ID = "f8e5d3c2-4b1a-4e7f-9c8d-2a3b4c5d6e7f"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


async def setup_banking_controls():
    """Create banking controls demonstrating observe, deny, and steer actions."""
    async with AgentControlClient(base_url=SERVER_URL) as client:
        # 1. Register Agent
        agent = Agent(
            agent_name="banking-transaction-agent",
            agent_description="AI agent that processes wire transfers with compliance and fraud controls"
        )

        try:
            await agents.register_agent(client, agent, steps=[])
            print(f"✓ Agent registered: {AGENT_ID}")
        except Exception as e:
            print(f"ℹ️  Agent might already exist: {e}")

        print("\n📋 Creating banking controls...")

        # ============================================================================
        # DENY CONTROLS - Hard blocks for compliance violations
        # ============================================================================

        # Control 1: Block Sanctioned Countries (DENY)
        sanctioned_countries_control = {
            "description": "Block transfers to OFAC sanctioned countries",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["process_wire_transfer"],
                "stages": ["pre"]
            },
            "condition": {
                "selector": {
                    "path": "input.destination_country"
                },
                "evaluator": {
                    "name": "list",
                    "config": {
                        "values": ["north korea", "iran", "syria", "cuba", "crimea"],
                        "logic": "any",
                        "match_mode": "contains",
                        "case_sensitive": False
                    }
                },
            },
            "action": {
                "decision": "deny"
            }
        }

        # Control 2: Block High Fraud Risk (DENY)
        fraud_risk_control = {
            "description": "Block transactions with high fraud risk scores",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["process_wire_transfer"],
                "stages": ["pre"]
            },
            "condition": {
                "selector": {
                    "path": "input"
                },
                "evaluator": {
                    "name": "json",
                    "config": {
                        "field_constraints": {
                            "fraud_score": {
                                "type": "number",
                                "max": 0.8
                            }
                        }
                    }
                },
            },
            "action": {
                "decision": "deny"
            }
        }

        # ============================================================================
        # OBSERVE CONTROLS - Record suspicious activity without blocking
        # ============================================================================

        # Control 3: New Recipient Audit (OBSERVE)
        new_recipient_control = {
            "description": "Observe transfers to new recipients for audit review",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
