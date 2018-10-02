#!/usr/bin/env python3
"""
Script to create, list, update, and manage controls on the server.

This script demonstrates the full control lifecycle:
1. Create an agent
2. Create controls (regex and list)
3. Associate controls directly with the agent
4. List controls
5. Update a control

API Structure:
    Agent → Controls

Prerequisites:
    - Agent Control server running at http://localhost:8000
    - Run: cd server && make run

Usage:
    uv run python examples/agent_control_demo/setup_controls.py
"""

import asyncio
import os
import sys

# Add the SDK to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../sdks/python/src"))

from agent_control import AgentControlClient


# Configuration
AGENT_NAME = "demo-chatbot"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


async def create_agent(client: AgentControlClient) -> str:
    """Create or get the demo agent."""
    print("\n" + "=" * 60)
    print("STEP 1: Creating Agent")
    print("=" * 60)

    try:
        response = await client.http_client.post(
            "/api/v1/agents/initAgent",  # Correct endpoint
            json={
                "agent": {
                    "agent_name": AGENT_NAME,
                    "agent_description": "Demo chatbot for testing controls",
                },
                "steps": []
            }
        )
        response.raise_for_status()
        data = response.json()

        created = data.get("created", False)

        if created:
            print(f"✓ Created new agent: {AGENT_NAME}")
        else:
            print(f"✓ Agent already exists: {AGENT_NAME}")

        print(f"  Agent Name: {AGENT_NAME}")
        return AGENT_NAME

    except Exception as e:
        print(f"✗ Failed to create agent: {e}")
        raise


async def create_control(
    client: AgentControlClient,
    name: str,
    control_definition: dict
) -> int:
    """Create a control with the given definition."""
    try:
        # Create and validate the control atomically.
        response = await client.http_client.put(
            "/api/v1/controls",
            json={"name": name, "data": control_definition},
        )

        if response.status_code == 409:
            # Control exists, get its ID
            print(f"  ℹ️  Control '{name}' already exists")
            # We need to find the control ID - for now, we'll re-create it
            # In a real app, you'd have a GET endpoint to find by name
            return -1

        response.raise_for_status()
        control_id = response.json().get("control_id")

        print(f"✓ Created control '{name}' with ID: {control_id}")
        return control_id

    except Exception as e:
        print(f"✗ Failed to create control '{name}': {e}")
        raise


async def create_regex_control(client: AgentControlClient) -> int:
    """Create a regex control to block SSN patterns."""
    print("\n" + "=" * 60)
    print("STEP 2: Creating Regex Control")
    print("=" * 60)

    control_definition = {
        "description": "Block SSN patterns in output to prevent PII leakage",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["post"]},  # Check AFTER
        "condition": {
            "selector": {"path": "output"},
            "evaluator": {
                "name": "regex",
                "config": {
                    "pattern": r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
                    "flags": []
                }
            },
        },
        "action": {"decision": "deny"},
        "tags": ["pii", "ssn", "output-filter"]
    }

    print(f"Creating control: block-ssn-output")
    print(f"  Type: Regex")
    print(f"  Pattern: {control_definition['condition']['evaluator']['config']['pattern']}")
    print(f"  Stages: {', '.join(control_definition['scope']['stages'])}")
    print(f"  Action: {control_definition['action']['decision']}")

    return await create_control(client, "block-ssn-output", control_definition)


async def create_list_control(client: AgentControlClient) -> int:
    """Create a list control to block dangerous SQL keywords."""
    print("\n" + "=" * 60)
    print("STEP 3: Creating List Control")
    print("=" * 60)

    control_definition = {
        "description": "Block dangerous SQL operations in input",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},  # Check BEFORE
