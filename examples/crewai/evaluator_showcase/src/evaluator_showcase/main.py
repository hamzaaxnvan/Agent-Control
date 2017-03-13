"""
CrewAI Data Analyst with All Four Built-in Evaluators.

Demonstrates every built-in Agent Control evaluator in a realistic
data-analyst scenario where a CrewAI crew queries databases and
generates reports:

  SQL   - Validates queries before execution (block DROP, enforce LIMIT)
  LIST  - Restricts access to sensitive tables (audit_log, salary_data)
  REGEX - Catches PII leaking through query results (SSN, emails)
  JSON  - Validates analysis requests (required fields, constraints)

PREREQUISITE:
    Run setup_controls.py first:

        $ uv run --active python setup_controls.py

    Then run this example:

        $ uv run --active evaluator_showcase

Scenarios:
    1. Safe SELECT query            -> SQL evaluator ALLOWS
    2. DROP TABLE injection         -> SQL evaluator DENIES
    3. Query without LIMIT          -> SQL evaluator DENIES
    4. Query sensitive table        -> LIST evaluator DENIES
    5. Query returns PII            -> REGEX evaluator DENIES (post-execution)
    6. Valid analysis request       -> JSON evaluator ALLOWS
    7. Missing required fields      -> JSON evaluator DENIES
    8. Missing purpose field        -> JSON evaluator STEERS (then allowed)
"""

import json
import os

import agent_control

from evaluator_showcase.tools import create_sql_tool, create_analysis_tool
from evaluator_showcase.crew import EvaluatorShowcaseCrew

# ── Configuration ───────────────────────────────────────────────────────
AGENT_NAME = "crewai-data-analyst"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

agent_control.init(
    agent_name=AGENT_NAME,
    agent_description="CrewAI data analyst with all evaluator types",
    server_url=SERVER_URL,
)


# ── Scenario Runner ─────────────────────────────────────────────────────

def verify_server():
    import httpx

    try:
        r = httpx.get(f"{SERVER_URL}/api/v1/controls?limit=100", timeout=5.0)
        r.raise_for_status()
        names = [c["name"] for c in r.json().get("controls", [])]
        required = [
            "sql-safety-check",
            "restrict-sensitive-tables",
            "pii-in-query-results",
            "validate-analysis-request",
            "steer-require-purpose",
        ]
        missing = [n for n in required if n not in names]
        if missing:
            print(f"Missing controls: {missing}")
            print("Run:  uv run --active python setup_controls.py")
            return False
        print(f"Server OK - {len(names)} controls active")
        return True
    except Exception as e:
        print(f"Cannot reach server at {SERVER_URL}: {e}")
        return False


def run_direct_test(title, evaluator, tool_fn, input_data, expected):
    """Run a test by calling the tool function directly (bypasses CrewAI LLM)."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"  Evaluator: {evaluator}")
    print(f"  Expected:  {expected}")
    print(f"{'=' * 60}")

    result = tool_fn.run(**input_data) if hasattr(tool_fn, 'run') else tool_fn(
        **input_data
    )
    print(f"\n  Result: {str(result)[:200]}")
    return result


def main():
    print("=" * 60)
    print("  CrewAI Data Analyst - Evaluator Showcase")
    print("  All 4 Built-in Evaluators: SQL, LIST, REGEX, JSON")
    print("=" * 60)
    print()

    if not verify_server():
        return

    if not os.getenv("OPENAI_API_KEY"):
        print("\nSet OPENAI_API_KEY to run the JSON/analysis scenarios.")
        print("SQL, LIST, and REGEX scenarios work without it.\n")

    sql_tool = create_sql_tool()
    analysis_tool = create_analysis_tool()

    # ════════════════════════════════════════════════════════════════
    #  SQL EVALUATOR SCENARIOS
    # ════════════════════════════════════════════════════════════════
    print("\n" + "#" * 60)
    print("  PART 1: SQL EVALUATOR")
    print("  Validates queries before they reach the database")
    print("#" * 60)

    # 1a. Safe query
    run_direct_test(
        "1a. Safe SELECT with LIMIT",
