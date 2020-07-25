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
