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
