#!/usr/bin/env python3
"""
Email Safety Demo - AgentControl + Steering

CRITICAL SCENARIO: Prevent PII leakage in automated customer emails

Shows two governance layers:
1. AgentControl (Safety): BLOCKS emails with PII, credentials, sensitive data
2. Steering (Quality): GUIDES agent to rephrase when PII detected

Flow:
  Customer: "Send password reset for account 123-45-6789"
  ↓
  LLM drafts: "We'll reset password for SSN 123-45-6789"
  ↓
  AgentControl: BLOCKS (contains PII)
  ↓
  Steering: GUIDES "Rephrase without PII"
  ↓
  LLM tries again: "We'll reset password for your account"
  ↓
  Email sent ✅

Usage:
    streamlit run email_safety_demo.py
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Import required modules
try:
    from strands import Agent, tool
    from strands.models.openai import OpenAIModel
    from strands.hooks import BeforeToolCallEvent, AfterToolCallEvent
    import agent_control
    from agent_control.integrations.strands import AgentControlPlugin, AgentControlSteeringHandler
    from agent_control.control_decorators import ControlViolationError
except ImportError as e:
    st.error(f"Missing dependency: {e}")
    st.stop()


# =============================================================================
# Mock Banking Tools
# =============================================================================

# Mock database of account information (contains PII!)
MOCK_ACCOUNTS = {
    "john@example.com": {
        "account_number": "123456789012",
        "name": "John Smith",
        "balance": 45234.56,
        "transactions": [
            {"date": "2/15", "type": "Deposit", "amount": 15000.00},
            {"date": "2/18", "type": "ATM Withdrawal", "amount": 200.00},
        ]
    },
    "sarah@example.com": {
        "account_number": "987654321098",
        "name": "Sarah Johnson",
        "ssn": "987-65-4321",
        "balance": 128456.78,
        "transactions": [
            {"date": "2/10", "type": "Wire Transfer", "amount": 50000.00},
            {"date": "2/20", "type": "Bill Payment", "amount": 1500.00},
        ]
    },
    "mike@example.com": {
        "account_number": "555123456789",
        "name": "Mike Davis",
        "ssn": "111-22-3333",
        "balance": 95432.10,
        "transactions": [
            {"date": "2/12", "type": "Direct Deposit", "amount": 25000.00},
            {"date": "2/17", "type": "ATM Withdrawal", "amount": 500.00},
        ]
    }
}

@tool
async def lookup_customer_account(customer_email: str) -> dict:
    """Look up customer account information from banking system.

    Args:
        customer_email: Customer's email address

    Returns:
        Account information including account number, balance, transactions, etc.
    """
    account_data = MOCK_ACCOUNTS.get(customer_email, {
        "account_number": "000000000000",
        "name": "Unknown Customer",
        "balance": 0.0,
        "transactions": []
    })

    print(f"\n📊 ACCOUNT LOOKUP: Retrieved data for {customer_email}")
    print(f"   Account: {account_data.get('account_number', 'N/A')}")
    print(f"   Balance: ${account_data.get('balance', 0):,.2f}")
    if account_data.get('ssn'):
        print(f"   ⚠️  SSN: {account_data['ssn']} (PII in database!)")
    print()

    return account_data

@tool
async def send_monthly_account_summary(
    customer_email: str,
    summary_text: str
) -> dict:
    """Send monthly account summary email to customer.

    IMPORTANT: Only call this tool AFTER the final email draft is approved and compliant.
    Do not call this during the drafting phase.

    Args:
        customer_email: Customer's email address
        summary_text: The summary email body text (final, redacted version)
    """
    print(f"\n📧 SENDING EMAIL to {customer_email}")
    print(f"   Preview: {summary_text[:100]}...")
    print()

    return {
        "success": True,
        "email_id": f"SUMMARY-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "sent_to": customer_email,
        "message": "Monthly account summary email sent successfully"
    }


# =============================================================================
# Initialize Agent
# =============================================================================

def initialize_agent():
    """Initialize email agent with dual-plugin AgentControl integration."""

    # Initialize AgentControl
    try:
        agent_control.init(
            agent_name="banking-email-agent",
            server_url=os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")
        )
    except Exception as e:
        if "409" not in str(e):
            raise

    # Plugin 1: AgentControlPlugin for tool-stage deny checks
    # Enforces hard blocks (credentials, internal info) at tool execution
    tool_plugin = AgentControlPlugin(
        agent_name="banking-email-agent",
        event_control_list=[BeforeToolCallEvent, AfterToolCallEvent],
        enable_logging=True
    )

    # Plugin 2: AgentControlSteeringHandler for LLM post-output steer
    # Guides PII redaction via Strands Guide() before tools are called
    steering_handler = AgentControlSteeringHandler(
        agent_name="banking-email-agent",
        enable_logging=True
    )

    # Create agent with both plugins
    model = OpenAIModel(model_id="gpt-4o-mini")
    agent = Agent(
        name="banking_email_agent",
        model=model,
        system_prompt="""You are a banking customer service assistant that sends automated monthly account summaries.

WORKFLOW (STRICT - TWO PHASES):
1. Look up account: Use lookup_customer_account() to retrieve account data
2. Draft email: Compose the email as plain text. Include account details (number, balance, transactions).
   - Do NOT call send_monthly_account_summary() yet
   - Just draft the email content
3. Send email: Call send_monthly_account_summary() with the final email text
4. Report success to the user

IMPORTANT:
- Phase 1: Draft the email BEFORE calling send tool
- Phase 2: Send the email AFTER draft is finalized
- If you receive guidance to redact information, revise the draft before sending
- Include specific account details in the email (these will be checked for PII)
- Be professional, clear, and reassuring
- NEVER mention technical errors, policy violations, or safety systems to customers

After sending, respond with:
