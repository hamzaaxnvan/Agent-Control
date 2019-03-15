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
        date_range = request.get("date_range", "")
        max_rows = request.get("max_rows", 1000)
        purpose = request.get("purpose", "")

        prompt = f"""Summarize this data analysis in 2-3 sentences:
- Dataset: {dataset}
- Date range: {date_range}
- Max rows: {max_rows}
- Purpose: {purpose}

Provide a brief, professional analysis summary."""

        return llm.call([{"role": "user", "content": prompt}])

    _analyze_data.name = "analyze_data"  # type: ignore[attr-defined]
    _analyze_data.tool_name = "analyze_data"  # type: ignore[attr-defined]
    controlled_fn = control()(_analyze_data)

    @tool("analyze_data")
    def analyze_data_tool(request: str) -> str:
        """Analyze a dataset with validation controls.

        Args:
            request: JSON string with fields: dataset (required), date_range (required),
                max_rows (optional, 1-10000), purpose (recommended for audit compliance)
        """
        if isinstance(request, dict):
            params = request
        else:
            try:
                params = json.loads(request)
            except (json.JSONDecodeError, TypeError):
                return f"Invalid request format. Expected JSON, got: {request!r}"

        # Build the request dict — only include fields that have values.
        # The JSON evaluator checks which fields are PRESENT in this dict,
        # so omitting a field triggers the "required_fields" check.
        request_dict: dict = {}
        if params.get("dataset"):
            request_dict["dataset"] = params["dataset"]
        if params.get("date_range"):
            request_dict["date_range"] = params["date_range"]
        if params.get("max_rows") is not None:
            request_dict["max_rows"] = int(params["max_rows"])
        if params.get("purpose"):
            request_dict["purpose"] = params["purpose"]

        print(f"\n  [ANALYSIS TOOL] Request: {request_dict}")

        # Steering retry loop
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                result = asyncio.run(controlled_fn(request=request_dict))
                print(f"  [ANALYSIS TOOL] Analysis complete")
