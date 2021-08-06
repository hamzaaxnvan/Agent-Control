"""
Banking Transaction Agent - AgentControl Steer Action Demo

An interactive banking assistant that demonstrates how AgentControl governs AI agents
in real-world scenarios with compliance, fraud detection, and approval workflows.

## What This Demo Shows

This agent processes wire transfers while AgentControl enforces:
- DENY actions for hard compliance violations (OFAC sanctions, high fraud)
- STEER actions for approval workflows (2FA verification, manager approval)
- OBSERVE actions for simple, low-risk transfer audit trails

## The Experience

You have a natural conversation with a banking agent:
  "Send $500 to Jane Smith" → ✅ Auto-approved
  "Wire $5k to North Korea" → ❌ Blocked (OFAC violation)
  "Transfer $15k to UK contractor" → 🔄 Guided through 2FA + manager approval

## How It Works

1. User requests a wire transfer in natural language
2. Agent parses the request and checks fraud risk
3. AgentControl evaluates 4 controls (2 DENY, 2 STEER)
4. If steered, agent prompts for 2FA/approval and retries
5. Transfer completes after all requirements are met

## Key Features

- Natural language parsing with GPT-4
- Real-time control evaluation via AgentControl server
- LLM-based steering context interpretation (agent reads control steering context and determines action)
- Human-in-the-loop for 2FA codes and manager approvals
- Autonomous retry logic with corrected parameters
- LangGraph state management for complex workflows

## Controls

- deny-sanctioned-countries: Blocks OFAC sanctioned destinations
- deny-high-fraud-risk: Blocks transactions with fraud score > 0.8
- steer-large-transfer-verification: Requires 2FA for transfers ≥ $10k
- steer-manager-approval-required: Requires approval for over-limit transfers

Run setup_controls.py first to create these controls on the server.
"""

import asyncio
import os
import time
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import agent_control
from agent_control import ControlSteerError, ControlViolationError, control

# Configuration
AGENT_ID = "f8e5d3c2-4b1a-4e7f-9c8d-2a3b4c5d6e7f"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"  # Set DEBUG=true to show technical error details


# =============================================================================
# UTILITIES
# =============================================================================

def agent_say(message: str, delay: float = 0.5):
    """Agent speaks with typing effect."""
    print(f"\n🤖 Agent: {message}")
    time.sleep(delay)


def agent_think(message: str):
    """Show agent thinking/processing."""
    print(f"   💭 {message}", end='', flush=True)
    time.sleep(0.8)
    print(" ✓")


def agent_reason(message: str):
    """Show agent internal reasoning in italic/dimmed style."""
    print(f"\033[3m\033[90m   🧠 Reasoning: {message}\033[0m")
    time.sleep(0.3)


def log_trace(category: str, message: str):
    """Log detailed trace information."""
    print(f"\033[2m   ⚙️  [{category.upper()}] {message}\033[0m")
    time.sleep(0.2)


def log_escalation(message: str):
    """Log when transferring to another person/system."""
    print(f"\n   🔄 \033[1m{message}\033[0m")
    time.sleep(0.5)


def user_input(prompt: str) -> str:
    """Get input from user."""
    return input(f"\n👤 You: {prompt}").strip()


def parse_steering_context(message: str) -> dict:
    """Parse structured steering context from JSON string.

    Returns a dict with:
    - required_actions: list of action strings
    - retry_flags: dict of flags to set for retry
    - reason: human-readable explanation
    - steps: optional list of step objects for multi-step workflows

    Falls back to empty structure if parsing fails.
    """
    try:
        import json
        parsed = json.loads(message)
        return parsed
    except (json.JSONDecodeError, ValueError):
        # Fallback for plain text steering context
        log_trace("parser", "Failed to parse steering context as JSON, using fallback")
        return {
            "required_actions": ["unknown"],
            "retry_flags": {},
            "reason": message
        }


def check_fraud_score(amount: float, destination: str) -> float:
    """Check fraud risk based on destination.

    Note: Amount thresholds are handled by steer controls, not here.
    Controls are the source of truth for transfer decisions.
    """
    agent_think("Running fraud detection...")
    if "north korea" in destination.lower() or "iran" in destination.lower():
        return 0.95
    else:
        return 0.1


# =============================================================================
# STATE
# =============================================================================

class AgentState(TypedDict):
    """Agent conversation state."""
    messages: Annotated[list, add_messages]
    transfer_request: dict | None
    fraud_score: float | None
    verified_2fa: bool
    manager_approved: bool
    justification: str | None
    final_result: dict | None
    status: str


# =============================================================================
# PROTECTED TOOL
# =============================================================================

@tool
def _process_wire_transfer(
    amount: float,
    destination_country: str,
    recipient_name: str,
    verified_2fa: bool = False,
    manager_approved: bool = False,
    justification: str | None = None,
