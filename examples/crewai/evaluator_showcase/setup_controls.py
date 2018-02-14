"""
Setup script for the CrewAI Evaluator Showcase.

Creates controls using ALL four built-in evaluators in a realistic
data-analyst agent scenario:

  REGEX - Block PII patterns (SSN, credit cards) in query results
  LIST  - Restrict access to sensitive database tables
  JSON  - Validate query parameters have required fields and constraints
  SQL   - Prevent dangerous SQL operations (DROP, DELETE, multi-statement)

Run once before running the demo:
    uv run --active python setup_controls.py
"""

import asyncio
import os

from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "crewai-data-analyst"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


async def setup():
    async with AgentControlClient(base_url=SERVER_URL) as client:
        # ── Register Agent ──────────────────────────────────────────────
        agent = Agent(
            agent_name=AGENT_NAME,
            agent_description=(
                "CrewAI data analyst agent that queries databases with "
                "controls on SQL safety, PII leakage, table access, and data validation"
            ),
        )

        try:
            await agents.register_agent(client, agent, steps=[])
            print(f"  Agent registered: {AGENT_NAME}")
        except Exception as e:
            if "already exists" in str(e).lower() or "409" in str(e):
                print(f"  Agent already registered: {AGENT_NAME}")
            else:
                raise

        # ── Control Definitions ─────────────────────────────────────────
        control_defs = [
            # ┌─────────────────────────────────────────────────────────┐
            # │  SQL EVALUATOR                                          │
            # │  Validates SQL queries for safety before execution.     │
            # │  Blocks DROP/DELETE/TRUNCATE, enforces LIMIT,           │
            # │  prevents multi-statement injection.                    │
            # └─────────────────────────────────────────────────────────┘
            (
                "sql-safety-check",
                {
                    "description": (
                        "Validate SQL queries: block destructive operations, "
                        "enforce LIMIT, prevent multi-statement injection"
                    ),
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["run_sql_query"],
                        "stages": ["pre"],
                    },
                    "condition": {
                        "selector": {"path": "input.query"},
                        "evaluator": {
                            "name": "sql",
                            "config": {
                                "blocked_operations": [
                                    "DROP",
                                    "DELETE",
                                    "TRUNCATE",
                                    "ALTER",
                                    "GRANT",
                                    "INSERT",
                                    "UPDATE",
                                ],
                                "allow_multi_statements": False,
                                "require_limit": True,
                                "max_limit": 100,
                            },
                        },
                    },
                    "action": {"decision": "deny"},
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  LIST EVALUATOR                                         │
            # │  Restricts which tables the agent can query.            │
            # │  Contains-match against the SQL query text to catch     │
            # │  references to sensitive tables.                        │
            # └─────────────────────────────────────────────────────────┘
            (
                "restrict-sensitive-tables",
                {
                    "description": (
                        "Block queries that reference sensitive tables: "
                        "audit_log, admin_users, payment_methods, salary_data"
                    ),
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["run_sql_query"],
                        "stages": ["pre"],
                    },
                    "condition": {
                        "selector": {"path": "input.query"},
                        "evaluator": {
                            "name": "list",
                            "config": {
                                "values": [
                                    "audit_log",
                                    "admin_users",
                                    "payment_methods",
                                    "salary_data",
                                ],
                                "logic": "any",
                                "match_mode": "contains",
                                "case_sensitive": False,
                            },
                        },
                    },
                    "action": {"decision": "deny"},
                },
            ),
            # ┌─────────────────────────────────────────────────────────┐
            # │  REGEX EVALUATOR                                        │
            # │  Scans query RESULTS for PII patterns after execution.  │
            # │  Catches SSNs, credit card numbers, and email           │
            # │  addresses that might leak through query results.       │
            # └─────────────────────────────────────────────────────────┘
            (
                "pii-in-query-results",
                {
                    "description": (
                        "Block query results containing PII: "
                        "SSN, credit card numbers, or email addresses"
                    ),
                    "enabled": True,
                    "execution": "server",
                    "scope": {
                        "step_types": ["tool"],
                        "step_names": ["run_sql_query"],
                        "stages": ["post"],
