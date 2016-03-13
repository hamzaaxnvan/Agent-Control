#!/usr/bin/env python3
"""
Setup script that creates demo controls for the Customer Support Agent.

This script:
1. Registers the agent with the server
2. Creates demo controls (PII detection, prompt injection)
3. Directly associates controls to the agent

Run this after starting the server to have a working demo out of the box.
"""

import asyncio
import os
from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "customer-support-agent"
AGENT_DESCRIPTION = "AI-powered customer support assistant"

SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

# Steps registered by support_agent.py (@control decorators). Registering them here
# ensures the UI steps dropdown is populated even if setup runs before the agent app.
DEMO_STEPS = [
    {"type": "llm", "name": "respond_to_customer"},
    {"type": "tool", "name": "lookup_customer"},
    {"type": "tool", "name": "search_knowledge_base"},
    {"type": "tool", "name": "create_ticket"},
]

# Demo controls to create
# Demonstrates selector paths plus scope.step_names / scope.step_name_regex targeting.
DEMO_CONTROLS = [
    # ==========================================================================
    # LLM CALL CONTROLS (using 'path' selector)
    # ==========================================================================
    {
        "name": "block-ssn-in-output",
        "description": "Blocks responses containing SSN patterns (path: output)",
        "definition": {
            "description": "Blocks responses containing SSN patterns (path: output)",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["post"]},
            "condition": {
                "selector": {"path": "output"},
                "evaluator": {
                    "name": "regex",
                    "config": {"pattern": r"\d{3}-\d{2}-\d{4}"},
                },
            },
            "action": {"decision": "deny"},
        },
    },
    {
        "name": "block-prompt-injection",
        "description": "Blocks common prompt injection attempts (path: input)",
        "definition": {
            "description": "Blocks common prompt injection attempts (path: input)",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["pre"]},
            "condition": {
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": r"(?i)(ignore.{0,20}(previous|prior|above).{0,20}instructions|you are now|system:|forget everything|disregard)"
                    },
                },
            },
            "action": {"decision": "deny"},
        },
    },
    {
        "name": "block-credit-card",
        "description": "Blocks messages containing credit card numbers (path: input)",
        "definition": {
            "description": "Blocks messages containing credit card numbers (path: input)",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["pre"]},
            "condition": {
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "regex",
                    "config": {"pattern": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"},
                },
            },
            "action": {"decision": "deny"},
        },
    },
    # ==========================================================================
    # TOOL CALL CONTROLS - using scope.step_names (exact match)
    # ==========================================================================
    {
        "name": "block-sql-injection-customer-lookup",
        "description": "Blocks SQL injection in customer lookup (scope.step_names: exact match)",
        "definition": {
            "description": "Blocks SQL injection in customer lookup (scope.step_names: exact match)",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["lookup_customer"],
                "stages": ["pre"],
            },
            "condition": {
                "selector": {
                    "path": "input.query",
                },
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": r"(?i)(select|insert|update|delete|drop|union|--|;)"
                    },
                },
            },
            "action": {"decision": "deny"},
        },
    },
    {
        "name": "observe-ticket-creation",
