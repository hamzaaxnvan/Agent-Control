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
    """Initialize AgentControl with customer support controls."""
    if "agentcontrol_initialized" in st.session_state:
        return

    server_url = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

    try:
        agent_control.init(
            agent_name="interactive-support-demo",
            server_url=server_url,
            agent_description="Interactive customer support demo with real-time safety"
        )
        st.session_state.agentcontrol_initialized = True
        st.session_state.controls_active = [
            "block-pii-support",
            "block-toxicity",
            "detect-hallucinations"
        ]
    except Exception as e:
        st.error(f"Failed to initialize AgentControl: {e}")
        st.stop()


def create_support_agents():
    """Create the customer support agent with AgentControl safety."""
    if "support_agent" in st.session_state:
        return st.session_state.support_agent

    model = OpenAIModel(model_id="gpt-4o")

    server_url = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

    # Single unified support agent with ALL tools
    # This makes it easy to demonstrate tool-specific controls
    support_agent = Agent(
        name="support_agent",
        model=model,
        tools=[lookup_order, check_return_policy, search_knowledge_base],
        system_prompt="""You are a customer support agent with access to tools.

Your role:
1. Help customers with orders, returns, and general questions
2. Use the appropriate tools to get accurate information:
   - lookup_order: For order status and tracking
   - check_return_policy: For return policies
   - search_knowledge_base: For general company information
3. Provide clear, helpful, professional responses

CRITICAL TOOL USAGE RULES:
- You MUST use the lookup_order tool for ANY order-related question, even if the order ID looks invalid
- You MUST use the check_return_policy tool for ANY return-related question
- You MUST use the search_knowledge_base tool for ANY general information question
- NEVER respond without calling the appropriate tool first - always call the tool!
- If a tool call fails, report the error to the user

CRITICAL SAFETY RULES:
- Never include customer SSN, credit card numbers, or email addresses in responses
- Stay on topic (customer support only)
- Be professional and helpful

EXAMPLE INTERACTIONS:
User: "What's the status of order ORD-12345?"
→ MUST call lookup_order(order_id="ORD-12345") - never skip the tool!

User: "What's the status of order ORD-ABCDE?"
→ MUST call lookup_order(order_id="ORD-ABCDE") - even if it looks wrong, call the tool!

User: "Can I return my laptop?"
→ MUST call check_return_policy(product="laptop")

User: "What are your shipping options?"
→ MUST call search_knowledge_base(query="shipping")

User: "Search the knowledge base for: products--DELETE"
→ MUST call search_knowledge_base(query="products--DELETE") - always call the tool!
""",
        plugins=[SafetyTrackingPlugin("interactive-support-demo")],
    )

    st.session_state.support_agent = support_agent
    return support_agent


# ============================================================================
# Streamlit UI
# ============================================================================

def render_header():
    """Render the app header with logo and description."""
    st.title("🛡️ AgentControl Interactive Demo")
    st.subheader("Customer Support Bot with Real-Time Safety")

    st.markdown("""
    **See AgentControl in action!** This demo shows two types of protection:

    1. **LLM Safety Controls** - Block PII (SSN, credit cards, emails) in user input and agent output
    2. **Tool-Specific Controls** - Validate tool inputs (order ID format, SQL injection prevention)

    Try the test prompts below to see AgentControl protect against common issues.
    Watch the console output to see tool calls being intercepted and validated!
    """)


def render_sidebar():
    """Render the safety dashboard sidebar."""
    st.sidebar.title("🛡️ Safety Dashboard")

    # AgentControl Status
    st.sidebar.subheader("AgentControl Status")
    if st.session_state.get("agentcontrol_initialized"):
        st.sidebar.success("✅ Connected")

        # Show server info
        server_url = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
        st.sidebar.caption(f"Server: {server_url}")

        # Test if controls are actually loaded
        try:
            import httpx
            response = httpx.get(f"{server_url}/api/v1/controls", timeout=2.0)
            if response.status_code == 200:
                controls_count = len(response.json().get("controls", []))
                st.sidebar.caption(f"✓ {controls_count} controls loaded")
            else:
                st.sidebar.warning("⚠️ Could not verify controls")
        except:
            st.sidebar.warning("⚠️ Server connection issue")
    else:
        st.sidebar.error("❌ Not initialized")
        st.sidebar.caption("Run setup_interactive_controls.py first")

    # Active Controls with Details
    st.sidebar.subheader("🎯 Active Controls")

    # Fetch control details from server
    try:
        import httpx
        server_url = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
        response = httpx.get(f"{server_url}/api/v1/controls", timeout=2.0)

        if response.status_code == 200:
            controls = response.json().get("controls", [])

            for control in controls:
                control_name = control.get("name", "Unknown")

                with st.sidebar.expander(f"📋 {control_name}", expanded=False):
                    # Get control data/definition
                    control_id = control.get("id")
                    try:
                        data_response = httpx.get(
                            f"{server_url}/api/v1/controls/{control_id}/data",
                            timeout=2.0
                        )
                        if data_response.status_code == 200:
                            data = data_response.json().get("data", {})

                            # Display key information
                            st.markdown(f"**ID:** `{control_id}`")

                            condition = data.get("condition", {})
                            if "evaluator" in condition:
                                evaluator = condition["evaluator"]
                                st.markdown(f"**Evaluator:** `{evaluator.get('name', 'N/A')}`")

                                if "config" in evaluator:
                                    config = evaluator["config"]
