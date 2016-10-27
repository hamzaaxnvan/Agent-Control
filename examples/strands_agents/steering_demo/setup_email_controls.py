#!/usr/bin/env python3
"""
Setup AgentControl safety controls for email demo.

CRITICAL CONTROLS:
- Block PII in email body (SSN, credit cards, phone numbers)
- Block credentials/secrets in email body
- Block internal system information

These are HARD BLOCKS (deny action) - critical for compliance (GDPR, PCI-DSS).
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env", override=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdks/python/src"))

from agent_control import Agent, AgentControlClient, agents, controls


# Configuration
AGENT_NAME = "banking-email-agent"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


# CRITICAL SAFETY CONTROLS
SAFETY_CONTROLS = [
    # Control 1: Detect PII in LLM output (draft) and steer redaction
    {
        "name": "steer-pii-redaction-llm-output",
        "description": "STEER: Guide PII redaction in LLM draft output",
        "definition": {
            "description": "Guide agent to redact PII in draft before tool call",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["llm"],
                "stages": ["post"]
            },
            "condition": {
                "selector": {"path": "output"},
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": r"(\b\d{9,12}\b)|(\d{3}[-\s]?\d{2}[-\s]?\d{4})|(\$[\d,]+\d{3,})"
                    }
                },
            },
            "action": {
                "decision": "steer",
                "steering_context": {
                    "message": """⚠️ FINANCIAL PII DETECTED - Apply redactions before sending email:

🔒 Redaction Rules (PCI-DSS Standard):
  • Account numbers: Mask all but last 4 digits
    Example: "123456789012" → "****9012" or "XXXX-XXXX-9012"
    Text format: "account ending in 9012" (no full number)

  • SSN: Remove entirely or mask all but last 4
    Example: "123-45-6789" → "***-**-6789" or remove completely
    Text format: "SSN ending in 6789" or omit

  • Large amounts (>$10,000): Round to nearest thousand
    Example: "$45,234.56" → "$45K" or "approximately $45,000"

  • Transaction amounts: Generalize without exact figures
    Example: "$15,000 deposit" → "recent deposit activity"

✅ Critical Requirements:
  - Show ONLY last 4 digits of account/card numbers
  - Mask or remove first 8+ digits completely
  - Never include full SSN, routing numbers, or PINs
  - Round large balances for privacy
  - Generalize transaction types without exact amounts
    """
                }
            },
            "tags": ["pii", "gdpr", "pci-dss", "steer", "llm"]
        }
    },

    # Control 2: Detect credentials/API keys (DENY - hard block)
    {
        "name": "deny-credentials",
        "description": "DENY: Block credentials or API keys in emails (HARD BLOCK)",
        "definition": {
            "description": "Prevent credential leakage - hard block if detected",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "stages": ["pre"],
                "step_names": ["send_monthly_account_summary"]
            },
            "condition": {
                "selector": {"path": "input.summary_text"},
                "evaluator": {
                    "name": "regex",
                    "config": {
                        # Match patterns like: api_key, password, secret, token
                        "pattern": r"(api[_-]?key|password|secret|token|credential)[\s:=]+['\"]?[\w\-]{8,}"
                    }
                },
            },
            "action": {"decision": "deny"},
            "tags": ["credentials", "secrets", "critical", "deny"]
        }
    },

    # Control 3: Detect internal system info (DENY - hard block)
    {
        "name": "deny-internal-info",
        "description": "DENY: Block internal system information in emails (HARD BLOCK)",
        "definition": {
            "description": "Prevent exposure of internal database names, server IPs - hard block",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "stages": ["pre"],
                "step_names": ["send_monthly_account_summary"]
            },
            "condition": {
                "selector": {"path": "input.summary_text"},
                "evaluator": {
                    "name": "regex",
                    "config": {
                        # Match database names, server paths
                        "pattern": r"(database|db_|server|localhost|127\.0\.0\.1|/var/|/etc/|C:\\\\)"
                    }
                },
            },
            "action": {"decision": "deny"},
            "tags": ["internal-info", "security", "deny"]
        }
    },
]


async def create_agent(client: AgentControlClient) -> str:
    """Create the email safety demo agent."""
    print("\n" + "=" * 70)
    print("STEP 1: Creating Email Safety Demo Agent")
    print("=" * 70)

    agent = Agent(
        agent_name=AGENT_NAME,
        agent_description="Email safety demo - prevents PII leakage in automated emails"
    )

    try:
        await agents.register_agent(client, agent, steps=[])
        print(f"✓ Agent registered: {AGENT_NAME}")
        return AGENT_NAME
    except Exception as e:
        print(f"ℹ️  Agent might already exist: {e}")
        return AGENT_NAME
