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
                                                    "exclusiveMaximum": 10000,
                                                }
                                            }
                                        },
                                        {
                                            "properties": {
                                                "amount": {
                                                    "type": "number",
                                                    "minimum": 10000,
                                                },
                                                "verified_2fa": {"const": True},
                                            }
                                        },
                                    ]
                                }
                            },
                        },
                    },
                    "action": {
                        "decision": "steer",
                        "steering_context": {
                            "message": (
                                '{"required_actions": ["verify_2fa"],'
                                ' "reason": "Transfers >= $10,000 require identity verification.'
                                " Please verify the customer's 2FA code before proceeding.\","
                                ' "retry_with": {"verified_2fa": true}}'
                            )
                        },
                    },
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  STEER: Very Large Transfer → Manager Approval         │
            # │  Uses JSON evaluator with oneOf schema.                │
            # │  Either amount < $50k OR amount >= $50k with approval. │
            # │  Multi-step: collect justification, then get approval. │
            # └─────────────────────────────────────────────────────────┘
            (
                "steer-require-manager-approval",
                {
                    "description": "Require manager approval for transfers >= $50,000",
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
                                                    "exclusiveMaximum": 50000,
                                                }
                                            }
                                        },
                                        {
                                            "properties": {
                                                "amount": {
                                                    "type": "number",
                                                    "minimum": 50000,
                                                },
                                                "manager_approved": {"const": True},
                                            }
                                        },
                                    ]
                                }
                            },
                        },
                    },
                    "action": {
                        "decision": "steer",
                        "steering_context": {
                            "message": (
                                '{"required_actions": ["collect_justification", "get_manager_approval"],'
                                ' "reason": "Transfers >= $50,000 require manager sign-off.'
                                " Collect a business justification from the requestor,"
                                ' then obtain manager approval before retrying.",'
                                ' "retry_with": {"manager_approved": true}}'
                            )
                        },
                    },
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  OBSERVE: New Recipient                                 │
            # │  Uses LIST evaluator with "not in" logic.              │
            # │  Records an advisory event when recipient is unknown   │
            # │  but does NOT block the transfer. Useful for audit.    │
            # └─────────────────────────────────────────────────────────┘
            (
                "observe-new-recipient",
                {
                    "description": "Observe transfers to unknown recipients",
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["process_transfer"],
                        "stages": ["pre"],
                    },
                    "condition": {
                        "selector": {"path": "input.recipient"},
                        "evaluator": {
                            "name": "list",
                            "config": {
                                "values": [
                                    "Acme Corp",
                                    "Global Suppliers Inc",
                                    "TechVentures LLC",
                                ],
                                "match_type": "not_in",
                                "case_sensitive": False,
                            },
                        },
                    },
                    "action": {"decision": "observe"},
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  OBSERVE: PII in Output                                 │
            # │  Uses REGEX evaluator to detect leaked PII in the      │
            # │  transfer confirmation. Records for compliance review. │
            # └─────────────────────────────────────────────────────────┘
            (
                "observe-pii-in-confirmation",
                {
                    "description": "Observe PII patterns in transfer confirmation output",
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
