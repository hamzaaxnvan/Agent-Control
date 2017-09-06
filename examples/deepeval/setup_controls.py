#!/usr/bin/env python3
"""
Setup script that creates DeepEval-based controls for the Q&A Agent.

This script:
1. Registers the agent with the server
2. Creates DeepEval GEval evaluator controls for quality checks
3. Directly associates controls to the agent

The controls demonstrate using DeepEval's LLM-as-a-judge to enforce:
- Response coherence
- Answer relevance
- Factual correctness

Run this after starting the server to have a working demo.
"""

import asyncio
import os
import sys
import httpx

# Add the current directory to the path so we can import the evaluator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and register the DeepEval evaluator
# This must be done before creating controls that use it
try:
    from evaluator import DeepEvalEvaluator

    print(f"✓ DeepEval evaluator loaded: {DeepEvalEvaluator.metadata.name}")

    # Note: We don't check is_available() here because the evaluator
    # may not be used immediately - it just needs to be registered
    # so the server knows about it when creating control definitions

except ImportError as e:
    print(f"❌ Error: Cannot import DeepEval evaluator: {e}")
    print("\nMake sure you're running from the examples/deepeval directory")
    print("and that agent-control-models is installed")
    sys.exit(1)

# Agent configuration
AGENT_NAME = "qa-agent-with-deepeval"
AGENT_DESCRIPTION = "Question answering agent with DeepEval quality controls"

SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

# DeepEval controls to create
DEEPEVAL_CONTROLS = [
    {
        "name": "check-coherence",
        "description": "Ensures LLM responses are coherent and logically consistent",
        "definition": {
            "description": "Ensures LLM responses are coherent and logically consistent",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["post"]},
            "condition": {
                "selector": {"path": "*"},
                "evaluator": {
                    "name": "deepeval-geval",
                    "config": {
                        "name": "Coherence",
                        "criteria": (
                            "Evaluate whether the response is coherent, logically consistent, "
                            "and well-structured. Check for contradictions and flow of ideas. "
                            "The response should make logical sense and not contain contradictory statements."
                        ),
                        "evaluation_params": ["input", "actual_output"],
                        "threshold": 0.6,
                        "model": "gpt-4o",
                        "strict_mode": False,
                        "verbose_mode": False,
                    },
                },
            },
            "action": {"decision": "deny"},
        },
    },
    {
        "name": "check-relevance",
        "description": "Ensures responses are relevant to the user's question",
        "definition": {
            "description": "Ensures responses are relevant to the user's question",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["post"]},
            "condition": {
                "selector": {"path": "*"},
                "evaluator": {
                    "name": "deepeval-geval",
                    "config": {
                        "name": "Relevance",
                        "criteria": (
                            "Determine whether the actual output is relevant and directly addresses "
                            "the input query. Check if it stays on topic and provides useful information "
                            "that answers the question asked."
                        ),
                        "evaluation_params": ["input", "actual_output"],
                        "threshold": 0.5,
                        "model": "gpt-4o",
                        "strict_mode": False,
                    },
                },
            },
            "action": {"decision": "deny"},
        },
    },
    {
        "name": "check-correctness",
        "description": "Validates factual correctness against expected answers (when available)",
        "definition": {
            "description": "Validates factual correctness against expected answers (when available)",
            "enabled": False,  # Disabled by default - enable when you have expected outputs
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["post"]},
            "condition": {
                "selector": {"path": "*"},
                "evaluator": {
                    "name": "deepeval-geval",
                    "config": {
                        "name": "Correctness",
                        "evaluation_steps": [
                            "Check whether facts in actual output contradict expected output",
                            "Heavily penalize omission of critical details",
                            "Minor wording differences are acceptable",
                            "Focus on factual accuracy, not style",
                        ],
                        "evaluation_params": ["actual_output", "expected_output"],
                        "threshold": 0.8,
                        "model": "gpt-4o",
                    },
                },
            },
            "action": {"decision": "observe"},
        },
    },
]


async def setup_demo(quiet: bool = False):
    """Set up the demo agent with DeepEval controls."""
    agent_name = AGENT_NAME

    print(f"Setting up agent: {AGENT_DESCRIPTION}")
    print(f"Agent name: {agent_name}")
    print(f"Server URL: {SERVER_URL}")
    print()

    async with httpx.AsyncClient(base_url=SERVER_URL, timeout=30.0) as client:
        # Check server health
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
            print("✓ Server is healthy")
        except httpx.HTTPError as e:
            print(f"❌ Error: Cannot connect to server at {SERVER_URL}")
            print(f"   {e}")
            print("\nMake sure the server is running")
            return False

        # Register the agent
        try:
            resp = await client.post(
                "/api/v1/agents/initAgent",
                json={
                    "agent": {
                        "agent_name": agent_name,
                        "agent_description": AGENT_DESCRIPTION,
                        "agent_version": "1.0.0",
                    },
                    "steps": [],
                },
            )
            resp.raise_for_status()
            result = resp.json()
            status = "Created" if result.get("created") else "Updated"
            print(f"✓ {status} agent: {agent_name}")
        except httpx.HTTPError as e:
            print(f"❌ Error registering agent: {e}")
            return False

        # Create controls and associate them directly with the agent
        print()
        print("Creating DeepEval controls...")
        controls_created = 0
        controls_updated = 0

        for control_spec in DEEPEVAL_CONTROLS:
            control_name = control_spec["name"]
            definition = control_spec["definition"]
            description = control_spec["description"]

            try:
                # Create and validate the control atomically.
                resp = await client.put(
                    "/api/v1/controls",
                    json={"name": control_name, "data": definition},
                )
                control_exists = resp.status_code == 409
                if control_exists:
                    # Control exists, get its ID
                    resp = await client.get("/api/v1/controls", params={"name": control_name})
                    resp.raise_for_status()
                    controls = [
                        control
                        for control in resp.json().get("controls", [])
                        if control.get("name") == control_name
                    ]
                    if controls:
                        control_id = controls[0]["id"]
                        controls_updated += 1
                    else:
