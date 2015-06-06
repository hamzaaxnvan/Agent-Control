"""
Customer Support Agent - Example Integration with Agent Control SDK

This module demonstrates how to integrate the agent-control SDK into
an existing customer support application. It shows:

1. SDK initialization at startup
2. Using @control() decorator to protect functions
3. Handling ControlViolationError gracefully
4. Realistic enterprise patterns (mock services, multiple tools)

NOTE: Controls are defined on the server via the UI, not in code.
This keeps security controls centrally managed and separate from code.
"""

import asyncio
import random
from datetime import datetime
from typing import Any

import agent_control
from agent_control import ControlViolationError, control
from agent_control.tracing import with_trace

AGENT_NAME = "customer-support-agent"
AGENT_DESCRIPTION = (
    "AI-powered customer support assistant that helps with inquiries, "
    "searches knowledge bases, and creates support tickets."
)


# =============================================================================
# SDK INITIALIZATION
# =============================================================================
# Call this once at the start of your application.
# The agent registers with the server and loads associated controls.


def initialize_agent_control() -> None:
    """Initialize the SDK once for this example process."""
    current_agent = agent_control.current_agent()
    if current_agent is not None and current_agent.agent_name == AGENT_NAME:
        return

    agent_control.init(
        agent_name=AGENT_NAME,
        agent_description=AGENT_DESCRIPTION,
        agent_version="1.0.0",
        observability_enabled=True,
    )


# =============================================================================
# MOCK SERVICES (Simulated - No External Dependencies)
# =============================================================================
# In a real application, these would connect to actual services.


class MockLLM:
    """Simulates an LLM for generating responses. No API key needed."""

    RESPONSES = {
        "greeting": "Hello! I'm your customer support assistant. How can I help you today?",
        "refund": "I understand you'd like a refund. Let me look into your order. "
                  "Our refund guidelines allow returns within 30 days of purchase.",
        "technical": "I can help with technical issues. Could you describe the problem "
                     "you're experiencing in more detail?",
        "status": "I'll check the status of your order right away. "
                  "Could you provide your order number?",
        "default": "Thank you for your message. Let me help you with that.",
    }

    @classmethod
    def generate(cls, message: str) -> str:
        """Generate a response based on message content."""
        message_lower = message.lower()

        if any(word in message_lower for word in ["hi", "hello", "hey"]):
            return cls.RESPONSES["greeting"]
        elif any(word in message_lower for word in ["refund", "return", "money back"]):
            return cls.RESPONSES["refund"]
        elif any(word in message_lower for word in ["error", "bug", "broken", "not working"]):
            return cls.RESPONSES["technical"]
        elif any(word in message_lower for word in ["status", "order", "tracking"]):
            return cls.RESPONSES["status"]
        else:
            return cls.RESPONSES["default"]


class CustomerDatabase:
    """Simulates a customer database lookup."""

    CUSTOMERS = {
        "C001": {
            "id": "C001",
            "name": "Alice Smith",
            "email": "alice@example.com",
            "tier": "premium",
            "orders": 15,
        },
        "C002": {
            "id": "C002",
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "tier": "standard",
            "orders": 3,
        },
        "alice@example.com": {
            "id": "C001",
            "name": "Alice Smith",
            "email": "alice@example.com",
            "tier": "premium",
            "orders": 15,
        },
    }

    @classmethod
    def lookup(cls, query: str) -> dict[str, Any] | None:
        """Look up a customer by ID or email."""
        return cls.CUSTOMERS.get(query)


class KnowledgeBase:
    """Simulates a RAG-style knowledge base search."""

    ARTICLES = [
        {
            "id": "KB001",
            "title": "How to Request a Refund",
            "content": "To request a refund, go to Orders > Select Order > Request Refund. "
                       "Refunds are processed within 5-7 business days.",
            "category": "billing",
        },
        {
            "id": "KB002",
            "title": "Resetting Your Password",
            "content": "Click 'Forgot Password' on the login page. Enter your email and "
                       "follow the instructions in the reset email.",
            "category": "account",
        },
        {
            "id": "KB003",
            "title": "Shipping Times and Tracking",
            "content": "Standard shipping takes 5-7 business days. Express shipping takes "
                       "2-3 business days. Track your order in the Orders section.",
            "category": "shipping",
        },
    ]

    @classmethod
    def search(cls, query: str) -> list[dict[str, Any]]:
        """Search for relevant knowledge base articles."""
        query_lower = query.lower()
        results = []

        for article in cls.ARTICLES:
            if (query_lower in article["title"].lower() or
