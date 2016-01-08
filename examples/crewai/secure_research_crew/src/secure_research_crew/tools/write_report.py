"""Writer tool: write_report -- generates reports with Agent Control PII protection and citation check."""

import asyncio
import json

from agent_control import ControlSteerError, ControlViolationError, control
from crewai.tools import tool

# ---------------------------------------------------------------------------
# Async inner function + @control() decorator
# ---------------------------------------------------------------------------

async def _write_report(content: str, sources: str = "") -> str:
    """Generate a formatted report. Protected by Agent Control.

    The @control decorator sends the output to the server for PII checking.
    """
    # Build the report body
    report = f"""Research Report
{'=' * 40}

{content}
"""
    if sources:
        report += f"""
Sources:
{sources}
"""
    return report


_write_report.name = "write_report"               # type: ignore[attr-defined]
_write_report.tool_name = "write_report"           # type: ignore[attr-defined]

_controlled_write_report = control()(_write_report)


# ---------------------------------------------------------------------------
# CrewAI @tool wrapper
# ---------------------------------------------------------------------------

@tool("write_report")
def write_report(content: str) -> str:
    """Generate the final research report. The content should NOT contain
    PII (social security numbers, email addresses, phone numbers).
    Include a 'Sources:' section at the end for citations.

    Args:
        content: The report body text, including a Sources section.
