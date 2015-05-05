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
    fraud_score: float | None = None
) -> dict:
    """Simulate wire transfer processing."""
    # This function is a placeholder and will be wrapped by AgentControl for enforcement.
    return {
        "status": "completed",
        "transaction_id": f"TXN-{hash(recipient_name) % 100000:05d}",
        "amount": amount,
        "destination": destination_country,
        "recipient": recipient_name
    } 

async def process_wire_transfer(
    amount: float,
    destination_country: str,
    recipient_name: str,
    verified_2fa: bool = False,
    manager_approved: bool = False,
    justification: str | None = None,
    fraud_score: float | None = None
) -> dict:
    """Execute wire transfer - gated by AgentControl."""
    agent_think("Executing wire transfer...")
    return _process_wire_transfer.invoke({
        "amount": amount,
        "destination_country": destination_country,
        "recipient_name": recipient_name,
        "verified_2fa": verified_2fa,
        "manager_approved": manager_approved,
        "justification": justification,
        "fraud_score": fraud_score
    })

# Mark wrapper as tool BEFORE applying @control so tool detection works
process_wire_transfer.name = "process_wire_transfer"  # type: ignore[attr-defined]
process_wire_transfer.tool_name = "process_wire_transfer"  # type: ignore[attr-defined]
process_wire_transfer = control(step_name="process_wire_transfer")(process_wire_transfer)

# =============================================================================
# AGENT LOGIC
# =============================================================================

async def parse_transfer_request(user_request: str) -> dict:
    """Parse natural language transfer request."""
    agent_think("Understanding your request...")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    parse_prompt = f"""Parse this wire transfer request into structured data.

User request: "{user_request}"

Examples:
- "Send $500 to Jane Smith" -> {{"amount": 500, "destination_country": "United States", "recipient_name": "Jane Smith"}}
- "Wire $15000 to contractor in UK" -> {{"amount": 15000, "destination_country": "United Kingdom", "recipient_name": "contractor"}}
- "Transfer $5k to North Korea" -> {{"amount": 5000, "destination_country": "North Korea", "recipient_name": "Unknown"}}

Extract these fields:
- amount: numeric dollar amount (e.g., 500, 15000, 5000)
- destination_country: full country name (if not mentioned, use "United States")
- recipient_name: person or company name (if not mentioned, use "Unknown")

IMPORTANT: Return ONLY valid JSON, no markdown, no explanation:
{{"amount": 500, "destination_country": "United States", "recipient_name": "Jane Smith"}}"""

    response = await llm.ainvoke([HumanMessage(content=parse_prompt)])

    import json
    import re

    try:
        # Clean up response - remove markdown code blocks if present
        content = response.content.strip()
        content = re.sub(r'^```json?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        parsed = json.loads(content)

        # Validate fields
        if not isinstance(parsed.get("amount"), (int, float)) or parsed["amount"] <= 0:
            raise ValueError("Invalid amount")

        return parsed

    except Exception as e:
        # Try regex fallback
        import re

        amount_match = re.search(r'\$?([\d,]+)k?', user_request, re.IGNORECASE)
        amount = 1000  # default

        if amount_match:
            amount_str = amount_match.group(1).replace(',', '')
            amount = float(amount_str)
            if 'k' in user_request.lower() and amount < 100:
                amount *= 1000

        # Extract recipient name (words after "to")
        recipient_match = re.search(r'to\s+([A-Za-z\s]+?)(?:\s+in|\s*$)', user_request, re.IGNORECASE)
        recipient = recipient_match.group(1).strip() if recipient_match else "Unknown"

        # Extract country
        country_match = re.search(r'in\s+([A-Za-z\s]+?)(?:\s+for|\s*$)', user_request, re.IGNORECASE)
        country = country_match.group(1).strip() if country_match else "United States"

        return {
            "amount": amount,
            "destination_country": country,
            "recipient_name": recipient
        }


async def process_transfer_node(state: AgentState) -> AgentState:
    """Main processing node."""
    request = state["transfer_request"]

    # Show what we're processing
    agent_say(f"Processing wire transfer:")
    print(f"   💵 Amount: ${request['amount']:,.2f}")
    print(f"   🌍 Destination: {request['destination_country']}")
    print(f"   👤 Recipient: {request['recipient_name']}")

    # Show if this is a retry with corrected flags
    if state.get("verified_2fa") or state.get("manager_approved"):
        print(f"\n   ♻️  \033[1mRETRY WITH CORRECTIONS:\033[0m")
        if state.get("verified_2fa"):
            print(f"      ✓ 2FA verified")
        if state.get("manager_approved"):
            print(f"      ✓ Manager approved")
        log_trace("retry", "Re-evaluating transfer with corrected authorization flags")

    # Check fraud if first time
    if state.get("fraud_score") is None:
        fraud_score = check_fraud_score(request["amount"], request["destination_country"])
        risk_level = "HIGH" if fraud_score > 0.7 else "MEDIUM" if fraud_score > 0.4 else "LOW"
        print(f"   🔍 Fraud Risk: {fraud_score:.2f} ({risk_level})")
        time.sleep(0.5)
    else:
        fraud_score = state["fraud_score"]

    agent_think("Checking compliance controls...")
    log_trace("agent-control", "Initiating pre-execution control evaluation")
    agent_reason("All transfers must pass control checks before execution")

    # DEBUG: Show what we're about to evaluate
    print(f"   🔍 DEBUG: Calling process_wire_transfer with:")
    print(f"      - step_name: 'process_wire_transfer'")
    print(f"      - amount: ${request['amount']:,.2f}")
    print(f"      - verified_2fa: {state.get('verified_2fa', False)}")
    print(f"      - manager_approved: {state.get('manager_approved', False)}")

    log_trace("agent-control", "Sending request to AgentControl server for evaluation")
    log_trace("agent-control", f"Evaluating against {4} active controls")

    try:
        # Attempt transfer - AgentControl gates this
        log_trace("execution", "Attempting wire transfer execution...")
        result = await process_wire_transfer(
            amount=request["amount"],
            destination_country=request["destination_country"],
            recipient_name=request["recipient_name"],
            verified_2fa=state.get("verified_2fa", False),
            manager_approved=state.get("manager_approved", False),
            justification=state.get("justification"),
            fraud_score=fraud_score
        )

        # Success!
        log_trace("agent-control", "All control checks passed ✓")
        log_trace("execution", "Wire transfer executed successfully")
        agent_reason("Transfer complies with all controls - proceeding with execution")

        # Show if this was a successful retry after steer correction
        if state.get("verified_2fa") or state.get("manager_approved"):
