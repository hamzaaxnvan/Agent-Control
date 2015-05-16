#!/usr/bin/env python3
"""
Demo agent that uses server-side controls.

This agent demonstrates how the @control decorator works
with controls defined on the server.

Prerequisites:
    1. Agent Control server running: cd server && make run
    2. Controls created: python setup_controls.py

Usage:
    python demo_agent.py
"""

import asyncio
import logging
import os
import sys

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

# Demo script logger
logger = logging.getLogger(__name__)

# Add the SDK to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../sdks/python/src"))

import agent_control
from agent_control import control, ControlViolationError


# Configuration
AGENT_NAME = "demo-chatbot"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


# =============================================================================
# SIMULATED LLM / BACKEND
# =============================================================================

def simulate_llm_response(query: str) -> str:
    """Simulate an LLM generating a response."""
    # This simulates various LLM responses, some containing sensitive data
