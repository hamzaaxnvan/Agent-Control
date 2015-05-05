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
        "condition": {
            "selector": {"path": "input"},
            "evaluator": {
                "name": "list",
                "config": {
                    "values": ["DROP", "DELETE", "TRUNCATE", "ALTER", "GRANT"],
                    "logic": "any",  # Block if ANY keyword is found
                    "match_on": "match",
                    "match_mode": "contains",  # Substring/keyword matching
                    "case_sensitive": False
                }
            },
        },
        "action": {"decision": "deny"},
        "tags": ["sql-injection", "input-filter", "security"]
    }

    print(f"Creating control: block-dangerous-sql")
    print(f"  Type: List")
    print(f"  Values: {control_definition['condition']['evaluator']['config']['values']}")
    print(f"  Logic: {control_definition['condition']['evaluator']['config']['logic']}")
    print(f"  Stages: {', '.join(control_definition['scope']['stages'])}")
    print(f"  Action: {control_definition['action']['decision']}")

    return await create_control(client, "block-dangerous-sql", control_definition)




async def add_control_to_agent(
    client: AgentControlClient,
    agent_name: str,
    control_id: int,
) -> bool:
    """Associate a control directly with an agent."""
    print("\n" + "=" * 60)
    print("STEP 4: Associating Control to Agent")
    print("=" * 60)

    try:
        response = await client.http_client.post(
            f"/api/v1/agents/{agent_name}/controls/{control_id}"
        )
        response.raise_for_status()
        data = response.json()
        print(f"✓ Associated control {control_id} to agent {agent_name}")
        print(f"  Response: {data}")
        return True
    except Exception as e:
        print(f"✗ Failed to associate control to agent: {e}")
        return False


async def list_agent_controls(client: AgentControlClient, agent_name: str) -> list:
    """List all controls for the agent."""
    print("\n" + "=" * 60)
    print("STEP 6: Listing Agent's Controls")
    print("=" * 60)

    try:
        response = await client.http_client.get(
            f"/api/v1/agents/{agent_name}/controls"
        )
        response.raise_for_status()
        data = response.json()
        controls = data.get("controls", [])

        print(f"✓ Found {len(controls)} control(s) for agent:\n")

        for ctrl in controls:
            print(f"  📋 Control: {ctrl.get('name', 'unnamed')}")
            print(f"     ID: {ctrl.get('id')}")
            ctrl_def = ctrl.get("control", {})
            print(f"     Enabled: {ctrl_def.get('enabled', True)}")
            evaluator_name = (
                ctrl_def.get("condition", {})
                .get("evaluator", {})
                .get("name", "unknown")
            )
            print(f"     Evaluator: {evaluator_name}")
            scope = ctrl_def.get("scope", {}) or {}
            stages = scope.get("stages", [])
            stage_label = ", ".join(stages) if stages else "unknown"
            print(f"     Stages: {stage_label}")
            print(f"     Action: {ctrl_def.get('action', {}).get('decision', 'unknown')}")
            print(f"     Tags: {ctrl_def.get('tags', [])}")
            print()

        return controls

    except Exception as e:
        print(f"✗ Failed to list controls: {e}")
        raise


async def update_control(client: AgentControlClient, control_id: int) -> None:
    """Update the list control to add more blocked keywords."""
    print("\n" + "=" * 60)
    print("STEP 7: Updating List Control")
    print("=" * 60)

    updated_definition = {
        "description": "Block dangerous SQL operations (UPDATED - more keywords)",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "condition": {
            "selector": {"path": "input"},
            "evaluator": {
                "name": "list",
                "config": {
                    "values": [
                        "DROP", "DELETE", "TRUNCATE", "ALTER", "GRANT",
                        "REVOKE", "EXECUTE", "SHUTDOWN", "BACKUP"  # More keywords!
                    ],
                    "logic": "any",
                    "match_on": "match",
                    "match_mode": "contains",  # Substring/keyword matching
                    "case_sensitive": False
                }
            },
        },
        "action": {"decision": "deny"},
        "tags": ["sql-injection", "input-filter", "security", "updated"]
    }

    print(f"Updating control ID: {control_id}")
    print(f"  Adding keywords: REVOKE, EXECUTE, SHUTDOWN, BACKUP")

    try:
        response = await client.http_client.put(
            f"/api/v1/controls/{control_id}/data",
            json={"data": updated_definition}
        )
        response.raise_for_status()
        print(f"✓ Successfully updated control {control_id}")
    except Exception as e:
        print(f"✗ Failed to update control: {e}")
        raise


async def get_control_data(client: AgentControlClient, control_id: int) -> dict:
    """Get a control's data."""
    print("\n" + "=" * 60)
    print("STEP 8: Getting Updated Control")
    print("=" * 60)

    try:
