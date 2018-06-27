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
    responses = {
        "user info": "The user's SSN is 456-22-6789 and their email is galileo@galileo.ai",
        "safe": "I'd be happy to help you with that question!",
        "help": "Here are some things I can assist you with...",
    }
    
    for key, response in responses.items():
        if key in query.lower():
            return response
    
    return f"I processed your query: {query}"


def simulate_database_query(sql: str) -> str:
    """Simulate a database query."""
    return f"Query executed: {sql}"


# =============================================================================
# AGENT FUNCTIONS WITH CONTROLS
# =============================================================================

@control()
async def chat(message: str) -> str:
    """
    Chat function protected by agent-associated controls.

    The 'block-ssn-output' control checks OUTPUT for SSN patterns.
    This prevents PII leakage in responses.
    """
    print(f"  [Agent] Processing message: {message}")
    response = simulate_llm_response(message)
    print(f"  [Agent] Generated response: {response[:50]}...")
    return response


@control()
async def execute_query(query: str) -> str:
    """
    Database query function protected by agent-associated controls.

    The 'block-dangerous-sql' control checks INPUT for dangerous
    SQL keywords and blocks before execution.
    """
    print(f"  [Agent] Executing query: {query}")
    result = simulate_database_query(query)
    print(f"  [Agent] Query result: {result}")
    return result


@control()  # Apply agent-associated controls
async def process_request(input: str) -> str:
    """
    General processing function with agent-associated controls applied.

    Controls directly associated to the agent are evaluated.
