"""LangGraph agent that relies on auto-derived step schemas from @control tools.

This example demonstrates the SDK flow we want:
1. Define tool-like functions with Python type hints.
2. Decorate them with ``@control()``.
3. Call ``agent_control.init(...)`` without explicit ``steps=...``.
4. Let the SDK auto-discover decorated functions and derive JSON Schemas.

Run:
    cd examples/langchain
    uv run langgraph_auto_schema_agent.py

Prerequisite:
    Start the Agent Control server (`cd server && make run`) so @control()
    evaluations can execute successfully at runtime.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Annotated, Literal, TypedDict

import agent_control
from agent_control import ControlViolationError, control, get_registered_steps
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

AGENT_NAME = "LangGraph Auto Schema Demo"
AGENT_DESCRIPTION = "LangGraph tool routing with @control auto step schema derivation"


class AgentState(TypedDict):
    """LangGraph state object."""

    messages: Annotated[list[BaseMessage], add_messages]


class OrderStatus(BaseModel):
    """Structured result for order status lookups."""

    order_id: str = Field(description="External order identifier")
    status: Literal["processing", "shipped", "delivered"]
    estimated_delivery_days: int | None = Field(
        default=None,
        ge=0,
        description="Days until delivery; null when already delivered",
    )
    history: list[str] = Field(default_factory=list)


class RefundDecision(BaseModel):
    """Structured result for refund checks."""

    order_id: str
    reason: Literal["damaged", "late", "cancelled"]
    approved: bool
    approved_amount: float = Field(ge=0)


class OrderStatusPayload(TypedDict):
    """Tool payload returned to LangGraph."""

    order_id: str
    status: Literal["processing", "shipped", "delivered"]
    estimated_delivery_days: int | None
    history: list[str]


class RefundDecisionPayload(TypedDict):
    """Tool payload returned to LangGraph."""

    order_id: str
    reason: Literal["damaged", "late", "cancelled"]
    approved: bool
    approved_amount: float


def _parse_order_id(user_text: str) -> str:
    """Extract a stable order identifier from user text."""
    match = re.search(r"(?:order\s*)?(\d{4,8})", user_text)
    if match:
        return f"ORD-{match.group(1)}"
    return "ORD-1001"


async def _lookup_order_status(order_id: str, include_history: bool = False) -> OrderStatus:
    """Fetch fulfillment status for an order."""
    base = OrderStatus(order_id=order_id, status="shipped", estimated_delivery_days=2)
    if include_history:
        base.history = [
            "Label created",
            "Picked up by carrier",
            "Arrived at regional hub",
        ]
    return base


setattr(_lookup_order_status, "name", "lookup_order_status")
setattr(_lookup_order_status, "tool_name", "lookup_order_status")
_lookup_order_status_checked = control()(_lookup_order_status)


async def _issue_refund(
    order_id: str,
    reason: Literal["damaged", "late", "cancelled"],
    requested_amount: float | None = None,
) -> RefundDecision:
    """Evaluate refund eligibility for an order."""
    approved_amount = requested_amount if requested_amount is not None else 25.0
    is_approved = approved_amount <= 100.0
    return RefundDecision(
        order_id=order_id,
        reason=reason,
        approved=is_approved,
        approved_amount=approved_amount if is_approved else 0.0,
    )


setattr(_issue_refund, "name", "issue_refund")
setattr(_issue_refund, "tool_name", "issue_refund")
_issue_refund_checked = control()(_issue_refund)


@tool("lookup_order_status")
async def lookup_order_status(order_id: str, include_history: bool = False) -> OrderStatusPayload:
    """LangGraph tool wrapper for order status."""
    result = await _lookup_order_status_checked(
        order_id=order_id,
        include_history=include_history,
    )
    return {
        "order_id": result.order_id,
        "status": result.status,
        "estimated_delivery_days": result.estimated_delivery_days,
