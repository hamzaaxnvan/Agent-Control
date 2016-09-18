"""
Secure Research Crew -- CrewAI multi-agent demo with per-agent Agent Control policies.

A 3-agent sequential crew where each agent has different controls:

  1. Researcher  -- queries a simulated database
     Controls: SQL evaluator (block DROP/DELETE, enforce LIMIT)
               LIST evaluator (block sensitive tables)

  2. Analyst    -- validates and processes research data
     Controls: JSON evaluator (require dataset, findings, confidence_score)
               JSON schema steer (add methodology if missing)

  3. Writer     -- generates the final report
     Controls: REGEX evaluator (block PII in output)
               Client-side citation check (steer if missing)

Scenarios:
  1. Happy path           -- all agents pass, report generated
  2. Researcher blocked   -- SQL injection attempt (DROP TABLE)
  3. Researcher restricted-- query to salary_data table
  4. Analyst steered      -- missing methodology, corrected, then succeeds
  5. Writer blocked       -- PII in report output

PREREQUISITE:
    uv run --active python setup_controls.py

Usage:
    uv run --active secure_research_crew
"""

import json
import os

import agent_control

# ---------------------------------------------------------------------------
# Configuration -- init must happen before tools are invoked (but can be
# after they are imported, since @control() is lazy).
# ---------------------------------------------------------------------------

AGENT_NAME = "secure-research-crew"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

agent_control.init(
    agent_name=AGENT_NAME,
    agent_description="Multi-agent research crew with per-agent policies",
    server_url=SERVER_URL,
)

# Import tools AFTER agent_control.init() -- the @control() decorator is
# applied at import time but does not call the server until invoked.
from secure_research_crew.tools.query_database import query_database  # noqa: E402
from secure_research_crew.tools.validate_data import validate_data  # noqa: E402
from secure_research_crew.tools.write_report import write_report  # noqa: E402


# ===========================================================================
# Scenario runners (direct tool calls -- avoids LLM costs for testing)
# ===========================================================================

def header(title: str) -> None:
    """Print a scenario header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_scenario_1_happy_path():
    """Happy path: all three tools pass controls, report generated."""
    header("SCENARIO 1: Happy Path -- All Agents Pass Controls")

    # Step 1: Researcher queries safely
    print("\n--- Step 1: Researcher queries database ---")
    data = query_database.run("SELECT name, department FROM employees LIMIT 10")
    print(f"  Result: {data[:120]}...")

    # Step 2: Analyst validates with all required fields + methodology
    print("\n--- Step 2: Analyst validates data ---")
    analysis_request = json.dumps({
        "dataset": "employees",
        "findings": "Engineering department has 2 senior staff members",
        "confidence_score": 0.92,
        "methodology": "Cross-referenced employee records with department roster",
    })
    validated = validate_data.run(analysis_request)
    print(f"  Result: {validated[:120]}...")

    # Step 3: Writer generates clean report
    print("\n--- Step 3: Writer generates report ---")
    report_content = (
        "The engineering department analysis reveals 2 senior staff members "
        "with strong project involvement. Project Alpha and Gamma are active "
        "with combined budgets exceeding $370,000. Quarterly revenue shows "
        "consistent 12-18% growth.\n\n"
        "Sources: Internal database (employees, projects, quarterly_metrics)"
    )
    report = write_report.run(report_content)
    print(f"  Result:\n{report}")


def run_scenario_2_sql_injection():
    """Researcher blocked: SQL injection attempt with DROP TABLE."""
    header("SCENARIO 2: Researcher Blocked -- SQL Injection Attempt")

    result = query_database.run("DROP TABLE employees; SELECT * FROM employees LIMIT 10")
    print(f"  Result: {result}")
    assert "BLOCKED" in result, "Expected the query to be blocked!"
    print("\n  [OK] SQL injection correctly blocked by data-access-policy")


def run_scenario_3_restricted_table():
    """Researcher restricted: query to salary_data table denied."""
    header("SCENARIO 3: Researcher Restricted -- Sensitive Table Access")

    result = query_database.run("SELECT * FROM salary_data LIMIT 10")
    print(f"  Result: {result}")
    assert "BLOCKED" in result, "Expected the query to be blocked!"
    print("\n  [OK] Sensitive table access correctly blocked by data-access-policy")


def run_scenario_4_analyst_steered():
    """Analyst steered: methodology missing, auto-corrected, then succeeds."""
    header("SCENARIO 4: Analyst Steered -- Missing Methodology")

    # First attempt WITHOUT methodology -- should be steered, then auto-corrected
    analysis_request = json.dumps({
        "dataset": "quarterly_metrics",
        "findings": "Revenue growing at 15% average quarterly rate",
        "confidence_score": 0.88,
        # NOTE: methodology intentionally omitted
    })
    result = validate_data.run(analysis_request)
    print(f"  Result: {result[:200]}...")

    # The tool should have auto-added methodology after steering
    if "validated" in result:
        print("\n  [OK] Analyst was steered to add methodology and succeeded on retry")
    elif "BLOCKED" in result:
        print("\n  [INFO] Analyst was blocked (deny control fired before steer)")
    else:
        print(f"\n  [INFO] Result: {result}")


def run_scenario_5_writer_pii():
    """Writer blocked: PII detected in report output."""
    header("SCENARIO 5: Writer Blocked -- PII in Report Output")

    # Content that contains PII (email and phone number)
