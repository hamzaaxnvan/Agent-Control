"""Data analysis tool with JSON validation and steering."""

import asyncio
import json
import os

from agent_control import ControlSteerError, ControlViolationError, control
from crewai import LLM
from crewai.tools import tool


def create_analysis_tool():
    """Build the analysis tool with JSON validation and steering."""

    # Defer LLM creation -- only needed if OPENAI_API_KEY is set
    llm = None
    if os.getenv("OPENAI_API_KEY"):
        llm = LLM(model="gpt-4o-mini", temperature=0.3)

    async def _analyze_data(request: dict) -> str:
        """Run data analysis (protected by JSON validation controls).

        Takes a single dict param so the @control() decorator sends it
        as input.request — and the JSON evaluator can check which fields
        are present or absent.
        """
        dataset = request.get("dataset", "")
