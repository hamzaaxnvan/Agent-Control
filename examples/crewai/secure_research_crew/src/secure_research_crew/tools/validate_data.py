"""Analyst tool: validate_data -- validates research data with Agent Control steering support."""

import asyncio
import json

from agent_control import ControlSteerError, ControlViolationError, control
from crewai.tools import tool

# ---------------------------------------------------------------------------
# Async inner function + @control() decorator
# ---------------------------------------------------------------------------

async def _validate_data(request: dict) -> str:
    """Validate and process research data. Protected by Agent Control.

    The request dict should contain:
      - dataset: str
      - findings: str
      - confidence_score: float (0-1)
      - methodology: str (optional, but will be steered if missing)
    """
    # If we reach here, controls passed -- produce analysis output
    return json.dumps({
        "status": "validated",
        "dataset": request.get("dataset"),
        "findings": request.get("findings"),
        "confidence_score": request.get("confidence_score"),
        "methodology": request.get("methodology", ""),
        "summary": (
            f"Analysis of '{request.get('dataset')}' confirms findings with "
            f"confidence {request.get('confidence_score')}. "
            f"Methodology: {request.get('methodology', 'N/A')}."
        ),
    }, indent=2)


_validate_data.name = "validate_data"             # type: ignore[attr-defined]
_validate_data.tool_name = "validate_data"         # type: ignore[attr-defined]

_controlled_validate_data = control()(_validate_data)


# ---------------------------------------------------------------------------
# CrewAI @tool wrapper
# ---------------------------------------------------------------------------

@tool("validate_data")
def validate_data(request_json: str) -> str:
    """Validate research data. Input must be a JSON string with fields:
    dataset (str), findings (str), confidence_score (float 0-1).
    A methodology field is recommended -- you will be asked to add one if missing.
