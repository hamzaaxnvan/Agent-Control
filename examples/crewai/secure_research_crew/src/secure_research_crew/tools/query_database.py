"""Researcher tool: query_database -- queries a simulated database with Agent Control protection."""

import asyncio
import json
import re

from agent_control import ControlViolationError, control
from crewai.tools import tool

# ---------------------------------------------------------------------------
# Simulated database (no real DB needed)
# ---------------------------------------------------------------------------

SIMULATED_DB = {
    "employees": [
        {"id": 1, "name": "Alice Johnson", "department": "Engineering", "role": "Senior Engineer"},
        {"id": 2, "name": "Bob Williams", "department": "Marketing", "role": "Marketing Lead"},
        {"id": 3, "name": "Carol Davis", "department": "Engineering", "role": "Staff Engineer"},
    ],
    "projects": [
        {"id": 101, "name": "Project Alpha", "status": "active", "budget": 150000},
        {"id": 102, "name": "Project Beta", "status": "completed", "budget": 80000},
        {"id": 103, "name": "Project Gamma", "status": "active", "budget": 220000},
    ],
    "quarterly_metrics": [
        {"quarter": "Q1", "revenue": 2400000, "growth": 0.12},
        {"quarter": "Q2", "revenue": 2700000, "growth": 0.15},
        {"quarter": "Q3", "revenue": 3100000, "growth": 0.18},
    ],
}


def simulate_query(query: str) -> str:
    """Return simulated data based on query content."""
    q = query.lower()
    if "employee" in q or "staff" in q:
        rows = SIMULATED_DB["employees"]
    elif "project" in q:
