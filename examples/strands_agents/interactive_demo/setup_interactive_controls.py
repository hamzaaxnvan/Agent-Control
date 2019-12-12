#!/usr/bin/env python3
"""
Setup script for Interactive Support Demo controls.

Creates 4 controls demonstrating AgentControl safety checks:
- User Input: Block PII and SQL injection patterns
- Agent Output: Block PII in responses
- Universal Tool Protection: Block PII in ALL tool inputs (step_types=["tool"])

Demonstrates different scoping patterns:
  • step_names=[...] - Target specific callbacks
  • step_types=["tool"] - Target ALL tool calls

Usage:
    python examples/strands_integration/interactive_demo/setup_interactive_controls.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Add the SDK to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdks/python/src"))

from agent_control import Agent, AgentControlClient, agents, controls


AGENT_NAME = "interactive-support-demo"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

INTERACTIVE_CONTROLS = [
    # User Input Controls - Block unsafe patterns in user messages
    {
        "name": "block-pii-input",
        "description": "Block PII in user input (SSN, credit cards, emails)",
        "definition": {
            "description": "Block PII patterns in user messages",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_names": ["check_before_invocation", "check_before_model"],
                "stages": ["pre"]
            },
            "condition": {
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b|\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
                    }
                },
            },
            "action": {"decision": "deny"},
            "tags": ["pii", "security"]
        }
    },
    {
