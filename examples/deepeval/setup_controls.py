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
