"""
Interactive Customer Support Demo with AgentControl

This Streamlit app demonstrates AgentControl's real-time safety features through
an interactive customer support chatbot. Users can chat with the bot and see
AgentControl block unsafe content in real-time.

VALUE DEMONSTRATION:
- Real-time PII protection (blocks SSN, credit cards, emails)
- Toxicity filtering (blocks rude/inappropriate language)
- Hallucination detection (prevents false information)
- Off-topic prevention (keeps conversations focused)
- Multi-agent safety (triage → specialist → response)

TRY TO BREAK IT:
The app includes "attack" prompts that demonstrate how AgentControl protects
against common safety issues. Watch the safety dashboard to see blocks in action!

Prerequisites:
    1. Agent Control server running:
       curl -fsSL https://raw.githubusercontent.com/agentcontrol/agent-control/docker-compose.yml | docker compose -f - up -d
    2. Controls created: python setup_interactive_controls.py
    3. OpenAI API key set
    4. Galileo API key set

Usage:
    streamlit run interactive_support_demo.py
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv

from strands import Agent, tool
from strands.hooks import (
    BeforeInvocationEvent,
    AfterModelCallEvent,
    BeforeToolCallEvent,
    AfterToolCallEvent,
)
from strands.models.openai import OpenAIModel

import agent_control
from agent_control import ControlSteerError, ControlViolationError
from agent_control.integrations.strands import AgentControlPlugin
from agent_control_models import EvaluationResult

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env", override=False)


# ============================================================================
# Safety Tracking Plugin (using reusable AgentControlPlugin)
# ============================================================================

def _action_error(result: EvaluationResult) -> tuple[str, Exception] | None:
    """
    Return the first blocking action as an exception.

    Args:
        result: EvaluationResult from AgentControl

    Returns:
        ("deny", ControlViolationError) or ("steer", ControlSteerError) if a blocking
        action is present, otherwise None.
    """
    match = next(
        (m for m in (result.matches or []) if m.action in ("deny", "steer")),
        None,
    )
    if not match:
        return None

    msg = getattr(getattr(match, "result", None), "message", None) or result.reason
    msg = msg or f"Control '{match.control_name}' triggered"

    if match.action == "deny":
        err = ControlViolationError(message=f"Policy violation [{match.control_name}]: {msg}")
        return "deny", err

    ctx = getattr(match, "steering_context", None)
    ctx_msg = getattr(ctx, "message", None) if ctx else None
    err = ControlSteerError(
        control_name=match.control_name,
        message=f"Steering required [{match.control_name}]: {msg}",
        steering_context=ctx_msg or msg,
    )
    return "steer", err


class SafetyTrackingPlugin(AgentControlPlugin):
    """
    Streamlit-specific plugin that extends AgentControlPlugin.

    Tracks all safety decisions and stores them in Streamlit session state for UI display.
    """

    def __init__(self, agent_name: str):
        """
        Initialize SafetyTrackingPlugin with Streamlit tracking.

        Args:
            agent_name: Name of the agent for logging and control filtering
        """
        # Initialize base AgentControlPlugin with specific events and custom callback
        super().__init__(
            agent_name=agent_name,
            event_control_list=[
                BeforeInvocationEvent,  # Check user input (has messages attribute)
                AfterModelCallEvent,    # Check output from LLM
                BeforeToolCallEvent,    # Check tool calls (enables tool-specific controls)
                AfterToolCallEvent,     # Check tool results
            ],
            on_violation_callback=self._handle_streamlit_violation,
            enable_logging=True  # Enable console logging to see control checks
        )

    def _initialize_session_state(self):
        """Initialize Streamlit session state if not already present."""
        if "stats" not in st.session_state:
            st.session_state.stats = {
                "checks_passed": 0,
                "violations_blocked": 0,
                "total_checks": 0
            }

        if "current_message_evaluations" not in st.session_state:
            st.session_state.current_message_evaluations = []

        if "current_message_violations" not in st.session_state:
            st.session_state.current_message_violations = []

    def _handle_streamlit_violation(self, violation_info: dict, _evaluation_result: Any):
        """
        Custom callback for updating Streamlit session state when violation detected.

        This is called by AgentControlPlugin whenever a safety violation occurs.
        """
        self._initialize_session_state()

        # Store detailed violation for UI
        violation = {
            "agent": violation_info["agent"],
            "controls": [violation_info["control_name"]],
            "stage": violation_info["stage"]
        }
        st.session_state.current_message_violations.append(violation)

        # Update violation stats
        st.session_state.stats["violations_blocked"] += 1

    async def _evaluate_and_enforce(
        self,
        step_name: str,
        input: Any | None = None,
        output: Any | None = None,
        context: dict[str, Any] | None = None,
        step_type: str = "llm",
        stage: str = "pre",
        violation_type: str = "Step",
        use_runtime_error: bool = False,
    ) -> None:
        """
        Override to add Streamlit-specific tracking for all checks.

        Tracks every check (pass or fail) in session state and stores
        detailed evaluation results for UI display.
        """
        self._initialize_session_state()
        st.session_state.stats["total_checks"] += 1

        result = await agent_control.evaluate_controls(
            step_name=step_name,
            input=input,
            output=output,
            step_type=step_type,
            stage=stage,
            agent_name=self.agent_name,
        )

        if result.is_safe:
            st.session_state.stats["checks_passed"] += 1

        try:
            evaluation_details = {
                "agent": self.agent_name,
                "stage": stage,
                "is_safe": result.is_safe,
                "matches": [
                    {
                        "control_name": m.control_name,
                        "confidence": m.result.confidence,
                        "message": m.result.message,
                        "metadata": m.result.metadata or {},
                    }
                    for m in (result.matches or [])
                ],
                "non_matches": [
                    {
                        "control_name": nm.control_name,
                        "confidence": nm.result.confidence,
                        "message": nm.result.message,
                        "metadata": nm.result.metadata or {},
                    }
                    for nm in (result.non_matches or [])
                ],
            }
            st.session_state.current_message_evaluations.append(evaluation_details)
        except Exception:
            pass

        action = _action_error(result)
        if action:
            _, err = action
            control_name = getattr(err, "control_name", "unknown")
            self._handle_streamlit_violation(
                {
                    "agent": self.agent_name,
                    "control_name": control_name,
                    "stage": stage,
                },
                result,
            )
            self._raise_error(err, use_runtime_error)

        if not result.is_safe:
            control_name = "unknown"
            reason = result.reason

            if result.matches:
                first_match = result.matches[0]
                control_name = first_match.control_name
                if not reason:
                    match_result = getattr(first_match, "result", None)
                    msg = getattr(match_result, "message", None) if match_result else None
                    reason = msg or f"Control '{control_name}' triggered"

            self._handle_streamlit_violation(
                {
                    "agent": self.agent_name,
                    "control_name": control_name,
                    "stage": stage,
                },
                result,
            )
            error_msg = f"Policy violation [{control_name}]: {reason}"
            self._raise_error(ControlViolationError(message=error_msg), use_runtime_error)


# ============================================================================
# Simulated Customer Support Tools
# ============================================================================

@tool
async def lookup_order(order_id: str) -> dict:
    """
    Look up order information.

    Args:
        order_id: The order ID to look up

    Returns:
        Order details including status and items
    """
    await asyncio.sleep(0.2)

    # Simulate order lookup
    orders = {
        "ORD-12345": {
            "status": "Shipped",
            "items": ["Laptop", "Mouse"],
            "total": "$1,299.99",
            "tracking": "TRK-98765"
        },
        "ORD-67890": {
            "status": "Processing",
            "items": ["Headphones"],
            "total": "$199.99",
            "tracking": "Not yet available"
        }
    }

    return orders.get(order_id, {"status": "Not found"})


@tool
async def check_return_policy(product: str) -> str:
    """
    Check the return policy for a product.

    Args:
        product: The product name

    Returns:
        Return policy information
    """
    await asyncio.sleep(0.1)
    return "30-day return policy for most items. Electronics have a 14-day return window."


@tool
async def search_knowledge_base(query: str) -> str:
    """
    Search the company knowledge base.

    Args:
        query: The search query

    Returns:
        Relevant information from knowledge base
    """
    await asyncio.sleep(0.2)

    kb = {
        "shipping": "Standard shipping: 5-7 business days. Express: 2-3 business days.",
        "warranty": "All products come with a 1-year manufacturer warranty.",
        "contact": "Email: support@example.com, Phone: 1-800-SUPPORT"
    }

    for key, value in kb.items():
        if key in query.lower():
            return value

    return "I couldn't find specific information. Please contact support."


# ============================================================================
# Initialize AgentControl and Create Agents
# ============================================================================

def initialize_agentcontrol():
