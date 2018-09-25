"""SQL query tool with @control protection."""

import asyncio

from agent_control import ControlViolationError, control
from crewai.tools import tool


# ── Simulated Database ──────────────────────────────────────────────────
# In a real app these would hit an actual database. The simulated responses
# let us demonstrate how Agent Control inspects both input AND output.

SIMULATED_RESULTS = {
    "safe": (
        "| order_id | product   | total  |\n"
        "|----------|-----------|--------|\n"
        "| 1001     | Widget A  | 29.99  |\n"
        "| 1002     | Widget B  | 49.99  |\n"
        "| 1003     | Gadget X  | 149.99 |\n"
        "\n3 rows returned."
    ),
    "pii": (
        "| customer_id | name       | ssn         | email              |\n"
        "|-------------|------------|-------------|--------------------|  \n"
        "| C-101       | John Smith | 123-45-6789 | john@example.com   |\n"
        "| C-102       | Jane Doe   | 987-65-4321 | jane@example.com   |\n"
        "\n2 rows returned."
    ),
}


def create_sql_tool():
    """Build the SQL query tool with @control protection."""

    async def _run_sql_query(query: str) -> str:
