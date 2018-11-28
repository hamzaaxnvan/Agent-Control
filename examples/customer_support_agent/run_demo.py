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
