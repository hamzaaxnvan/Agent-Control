"""Transfer tool with @control() protection and steering retry logic."""

import asyncio
import json

from agent_control import ControlSteerError, ControlViolationError, control
from crewai import LLM
from crewai.tools import tool

# Simulated state — in production this comes from your auth system
SIMULATED_2FA_CODE = "482901"
SIMULATED_MANAGER = "Sarah Chen (VP Operations)"


def create_transfer_tool():
    """Build the CrewAI tool with @control protection and steering logic."""

    llm = LLM(model="gpt-4o-mini", temperature=0.3)

    async def _process_transfer(
        amount: float,
        recipient: str,
        destination_country: str,
        fraud_score: float = 0.0,
        verified_2fa: bool = False,
        manager_approved: bool = False,
    ) -> str:
        """Process a wire transfer (protected by Agent Control)."""
        prompt = f"""You are a banking operations system. Process this wire transfer
and return a short confirmation message (2-3 sentences).

Transfer details:
- Amount: ${amount:,.2f}
- Recipient: {recipient}
- Destination: {destination_country}
- 2FA verified: {verified_2fa}
- Manager approved: {manager_approved}

Return a professional confirmation with a reference number."""

