"""
Setup script for the Secure Research Crew controls and policies.

Creates three policies (one per crew agent) with distinct controls:
  - data-access-policy         (Researcher): SQL safety + restricted table list
  - analysis-validation-policy (Analyst):    JSON field validation + steer on missing methodology
  - content-safety-policy      (Writer):     PII regex blocking

All controls are also directly associated with the runtime agent
("secure-research-crew") for immediate enforcement. The policies provide
organizational grouping and can be managed independently on the server.

This script is fully idempotent -- safe to run multiple times.

Usage:
    uv run --active python setup_controls.py
"""

import asyncio
import os

from agent_control import Agent, AgentControlClient, agents, controls, policies

AGENT_NAME = "secure-research-crew"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_control_idempotent(client, name: str, data: dict) -> int:
    """Create a control, handling 409 conflicts gracefully.

    On conflict, looks up the existing control by name and updates its data
    to ensure the configuration matches the desired state.
    """
    try:
        result = await controls.create_control(client, name=name, data=data)
        control_id = result["control_id"]
        print(f"  + Created control: {name} (ID: {control_id})")
        return control_id
    except Exception as e:
        if "409" in str(e):
            controls_list = await controls.list_controls(client, name=name, limit=1)
            if controls_list["controls"]:
                control_id = controls_list["controls"][0]["id"]
                await controls.set_control_data(client, control_id, data)
                print(f"  ~ Control exists: {name} (ID: {control_id}) -- data updated")
                return control_id
            raise RuntimeError(f"409 conflict but could not find control '{name}'")
        raise


async def create_policy_safe(client, name: str) -> int | None:
    """Create a policy. Returns the ID on success, None on 409 conflict.

    The server does not expose a list-policies-by-name endpoint, so on
    conflict we cannot reliably retrieve the existing policy ID. In that
    case we return None and the caller uses direct agent-control associations
    as a fallback (which are always idempotent).
    """
    try:
        result = await policies.create_policy(client, name=name)
        policy_id = result["policy_id"]
        print(f"  + Created policy: {name} (ID: {policy_id})")
        return policy_id
    except Exception as e:
        if "409" in str(e):
            print(f"  ~ Policy already exists: {name} (skipping policy-level association)")
            # Try to extract policy_id from error response body
            if hasattr(e, "response"):
                try:
                    body = e.response.json()
                    if "policy_id" in body:
                        return body["policy_id"]
                except Exception:
                    pass
            return None
        raise


# ---------------------------------------------------------------------------
# Control definitions
# ---------------------------------------------------------------------------

def researcher_controls() -> list[tuple[str, dict]]:
    """Controls for the Researcher agent's query_database tool."""
    sql_safety = {
        "description": "Block dangerous SQL operations and enforce LIMIT clause",
        "enabled": True,
        "execution": "server",
        "scope": {
            "step_types": ["tool"],
            "step_names": ["query_database"],
            "stages": ["pre"],
        },
        "condition": {
            "selector": {"path": "input.query"},
            "evaluator": {
                "name": "sql",
                "config": {
                    "blocked_operations": ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"],
                    "allow_multi_statements": False,
                    "require_limit": True,
                    "max_limit": 100,
                },
            },
        },
        "action": {"decision": "deny"},
    }

    restricted_tables = {
        "description": "Block access to sensitive tables (salary_data, admin_users, credentials)",
        "enabled": True,
        "execution": "server",
        "scope": {
            "step_types": ["tool"],
            "step_names": ["query_database"],
            "stages": ["pre"],
        },
        "condition": {
            "selector": {"path": "input.query"},
            "evaluator": {
                "name": "list",
                "config": {
                    "values": ["salary_data", "admin_users", "credentials", "auth_tokens"],
                    "logic": "any",
                    "match_mode": "contains",
                    "case_sensitive": False,
                },
            },
        },
        "action": {"decision": "deny"},
    }

    return [
        ("researcher-sql-safety", sql_safety),
        ("researcher-restricted-tables", restricted_tables),
    ]


def analyst_controls() -> list[tuple[str, dict]]:
    """Controls for the Analyst agent's validate_data tool."""
    required_fields = {
        "description": "Require dataset, findings, and confidence_score in analysis",
        "enabled": True,
        "execution": "server",
        "scope": {
            "step_types": ["tool"],
            "step_names": ["validate_data"],
            "stages": ["pre"],
        },
        "condition": {
            "selector": {"path": "input.request"},
            "evaluator": {
                "name": "json",
                "config": {
                    "required_fields": ["dataset", "findings", "confidence_score"],
                    "field_constraints": {
                        "confidence_score": {
                            "type": "number",
                            "min": 0,
                            "max": 1,
                        }
                    },
                },
            },
        },
        "action": {"decision": "deny"},
    }

    missing_methodology = {
        "description": "Steer analyst to add methodology when missing",
        "enabled": True,
        "execution": "server",
        "scope": {
            "step_types": ["tool"],
            "step_names": ["validate_data"],
            "stages": ["pre"],
        },
        "condition": {
            "selector": {"path": "input.request"},
            "evaluator": {
                "name": "json",
                "config": {
                    "json_schema": {
                        "type": "object",
                        "oneOf": [
                            {
                                "required": ["methodology"],
                                "properties": {
                                    "methodology": {"type": "string", "minLength": 1}
                                },
                            }
                        ],
                    }
                },
            },
        },
        "action": {
            "decision": "steer",
            "steering_context": {
                "message": (
                    '{"required_actions": ["add_methodology"], '
                    '"reason": "Analysis must include a methodology section '
                    'describing how data was collected and validated.", '
                    '"retry_with": {"methodology": '
                    '"<describe your data collection and validation method>"}}'
                )
            },
        },
    }

    return [
        ("analyst-required-fields", required_fields),
        ("analyst-methodology-check", missing_methodology),
    ]


def writer_controls() -> list[tuple[str, dict]]:
    """Controls for the Writer agent's write_report tool."""
    pii_regex = {
        "description": "Block PII (SSN, email, phone) in report output",
        "enabled": True,
        "execution": "server",
        "scope": {
            "step_types": ["tool"],
            "step_names": ["write_report"],
            "stages": ["post"],
        },
        "condition": {
            "selector": {"path": "output"},
            "evaluator": {
                "name": "regex",
                "config": {
                    "pattern": (
                        r"(?:"
                        r"\b\d{3}-\d{2}-\d{4}\b"           # SSN
                        r"|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"  # Email
                        r"|\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"  # Phone
                        r")"
                    )
                },
            },
        },
        "action": {"decision": "deny"},
    }
