#!/usr/bin/env python3
"""
Customer Support Agent Demo Runner

Interactive demo showing the agent-control SDK integration.

Usage:
    python run_demo.py              # Interactive chat mode (default)
    python run_demo.py --automated  # Run automated test scenarios
    python run_demo.py --reset      # Reset agent (remove control associations) and exit

Test Commands (in interactive mode):
    /test-safe          Run safe message tests
    /test-pii           Test PII detection (if control configured)
    /test-injection     Test prompt injection detection (if control configured)
    /test-multispan     Test multi-span traces (2-3 spans per request)
    /test-tool-controls Test tool-specific controls (step_names, step_name_regex)
    /lookup <query>     Look up a customer (e.g., /lookup C001)
    /search <query>     Search knowledge base (e.g., /search refund)
    /ticket [priority]  Create a test ticket (e.g., /ticket high)
    /comprehensive      Run comprehensive support flow (multi-span)
    /help               Show available commands
    /quit               Exit the demo
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import TYPE_CHECKING

import agent_control
from agent_control import AgentControlClient, agents, controls

if TYPE_CHECKING:
    from support_agent import CustomerSupportAgent

# Configure logging to see SDK debug output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Enable SDK logs at DEBUG level to see all control evaluations
logging.getLogger('agent_control').setLevel(logging.DEBUG)

# Suppress noisy HTTP library logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# Demo script logger - separate from SDK logger
# This demonstrates that SDK logging doesn't override application logging
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

AGENT_NAME = "customer-support-agent"


async def reset_agent():
    """Reset the agent by removing direct control associations."""
    server_url = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

    logger.info(f"Resetting agent '{AGENT_NAME}'")
    print(f"Resetting agent '{AGENT_NAME}'...")
    print()

    async with AgentControlClient(base_url=server_url) as client:
        # Check if agent exists
        try:
            await agents.get_agent(client, AGENT_NAME)
            logger.debug("Agent exists, proceeding with reset")
        except Exception as e:
            if "404" in str(e):
                logger.info("Agent not found in database")
                print("Agent not found - nothing to reset.")
                return
            logger.error(f"Error checking agent: {e}")
            print(f"Error checking agent: {e}")
            return

        # Remove direct control associations (idempotent per control ID).
        removed_direct_associations = 0
        cursor: int | None = None
        while True:
            controls_page = await controls.list_controls(client, cursor=cursor, limit=100)
            control_summaries = controls_page.get("controls", [])

            for summary in control_summaries:
                control_id = summary.get("id")
                if control_id is None:
                    continue
                try:
                    remove_result = await agents.remove_agent_control(
                        client,
                        AGENT_NAME,
                        control_id,
                    )
                    if remove_result.get("removed_direct_association"):
                        removed_direct_associations += 1
                except Exception as e:
                    # Ignore transient 404s while iterating controls; keep best-effort cleanup.
                    if "404" not in str(e):
                        logger.debug(
                            "Error removing direct control %s from %s: %s",
                            control_id,
                            AGENT_NAME,
                            e,
                        )

            pagination = controls_page.get("pagination", {})
            next_cursor = pagination.get("next_cursor")
            if next_cursor is None:
                break
            cursor = int(next_cursor)

        print(
            f"Removed {removed_direct_associations} direct control association(s) from agent."
        )

    print()
    print("Reset complete. The agent now has no direct control associations.")
    print("Run the demo again and add controls via the UI to test.")


# Import after defining reset functions to avoid SDK initialization on --reset
def get_agent() -> CustomerSupportAgent:
    from support_agent import CustomerSupportAgent
    return CustomerSupportAgent()


def print_header():
    """Print the demo header."""
    print()
    print("=" * 70)
    print("  Customer Support Agent - Agent Control SDK Demo")
    print("=" * 70)
    print()
    print("This demo shows how the agent-control SDK protects an AI agent.")
    print("Controls are configured on the server via the UI - not in code.")
    print()
    print("Features demonstrated:")
    print("  • Multi-span traces (2-3 spans per request)")
    print("  • Control targeting: selector paths plus scope.step_names / scope.step_name_regex")
    print("  • Various control types: LLM calls and tool calls")
    print()
    print("Commands:")
    print("  /help               Show all commands")
    print("  /test-multispan     Test multi-span traces")
    print("  /test-tool-controls Test tool-specific controls")
    print("  /comprehensive      Run full support flow (multi-span)")
    print("  /quit               Exit")
    print()
    print("-" * 70)
    print()


def print_help():
    """Print help information."""
    print()
    print("Available Commands:")
    print("  /help                Show this help message")
    print()
    print("Test Suites:")
    print("  /test-safe           Test normal, safe interactions")
    print("  /test-pii            Test PII detection control")
    print("  /test-injection      Test prompt injection control")
    print("  /test-multispan      Test multi-span traces (2-3 spans per request)")
    print("  /test-tool-controls  Test tool-specific controls (step_names, step_name_regex)")
    print()
    print("Tools (single span each):")
    print("  /lookup <query>      Look up customer (e.g., /lookup C001)")
    print("  /search <query>      Search knowledge base (e.g., /search refund)")
    print("  /ticket [priority]   Create support ticket (e.g., /ticket high)")
    print()
    print("Multi-Span Flows:")
    print("  /comprehensive [customer_id] <message>")
    print("                       Run full support flow: lookup → search → respond")
    print("                       Creates 2-3 spans in a single trace")
    print("                       Example: /comprehensive C001 I need a refund")
    print()
    print("  /quit or /exit       Exit the demo")
    print()
    print("Or just type a message to chat with the support agent (single span).")
    print()


async def run_interactive(agent: CustomerSupportAgent):
    """Run the interactive chat mode."""
    logger.info("Starting interactive demo mode")
    print_header()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            logger.info("User interrupted, exiting interactive mode")
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            command = user_input.lower().split()[0]
            args = user_input[len(command):].strip()
            logger.debug(f"Processing command: {command}")

            if command in ("/quit", "/exit"):
                print("Goodbye!")
                break

            elif command == "/help":
                print_help()

            elif command == "/test-safe":
                await run_safe_tests(agent)

            elif command == "/test-pii":
                await run_pii_tests(agent)

            elif command == "/test-injection":
                await run_injection_tests(agent)

            elif command == "/test-multispan":
                await run_multispan_tests(agent)

            elif command == "/test-tool-controls":
                await run_tool_control_tests(agent)

            elif command == "/comprehensive":
                # Parse: /comprehensive [customer_id] message
                # Customer ID starts with C (e.g., C001)
                parts = args.split(maxsplit=1)
                customer_id = None
                message = args

                if parts and parts[0].upper().startswith("C") and len(parts[0]) <= 6:
                    customer_id = parts[0].upper()
                    message = parts[1] if len(parts) > 1 else "I need help"

                if not message:
                    print("Usage: /comprehensive [customer_id] <message>")
                    print("Example: /comprehensive C001 I need help with a refund")
                else:
                    print("Running comprehensive support flow (multi-span)...")
                    if customer_id:
                        print(f"  Customer: {customer_id}")
                    print(f"  Message: {message}")
                    print()
