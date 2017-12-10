"""
Setup script for Content Publishing Flow controls.

Creates Agent Control controls for each stage of the CrewAI Flow pipeline:
- Intake: JSON evaluator to validate required fields
- Research: LIST evaluator to block banned sources
- Fact-Check: REGEX evaluator to flag unverified claims
- Draft: REGEX evaluator for PII, LIST evaluator for banned topics
- Compliance: JSON evaluator for legal review fields
- Editor: REGEX for PII cleanup (executive summary check is client-side)
- Human Review: STEER action for manager approval on internal memos

Run once before running publishing_flow.py:
    uv run --active python setup_controls.py
"""

import asyncio
import os

from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "content-publishing-flow"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


async def create_control_safe(
    client: AgentControlClient,
    name: str,
    data: dict,
) -> int:
    """Create a control, handling 409 conflicts gracefully. Returns control_id."""
    try:
        result = await controls.create_control(client, name=name, data=data)
        control_id = result["control_id"]
        print(f"  + Created control: {name} (ID: {control_id})")
        return control_id
    except Exception as e:
        if "409" in str(e):
            print(f"  ~ Control '{name}' already exists, looking it up...")
            controls_list = await controls.list_controls(client, name=name, limit=1)
            if controls_list["controls"]:
                control_id = controls_list["controls"][0]["id"]
                print(f"  ~ Using existing control (ID: {control_id})")
                return control_id
            else:
                print(f"  ! Could not find existing control '{name}'")
                raise SystemExit(1)
        else:
            detail = getattr(getattr(e, "response", None), "text", "")
            print(f"  ! Error creating control '{name}': {e}\n  ! Response body: {detail}")
            raise


async def add_control_to_agent_safe(
    client: AgentControlClient,
    agent_name: str,
    control_id: int,
    control_name: str,
) -> None:
    """Associate a control with an agent, handling duplicates gracefully."""
    try:
        await agents.add_agent_control(client, agent_name, control_id)
        print(f"  + Associated '{control_name}' with agent")
    except Exception as e:
        if "409" in str(e) or "already" in str(e).lower():
            print(f"  ~ '{control_name}' already associated with agent (OK)")
        else:
            print(f"  ! Failed to associate '{control_name}': {e}")
            raise


async def setup_publishing_controls():
    """Create all controls for the content publishing flow pipeline."""
    async with AgentControlClient(base_url=SERVER_URL) as client:

        # =====================================================================
        # 1. Register the Agent
        # =====================================================================
        print("Registering agent...")
        agent = Agent(
            agent_name=AGENT_NAME,
            agent_description=(
                "Content publishing flow with routing, embedded crews, "
                "and Agent Control guardrails at each pipeline stage"
            ),
        )

        try:
            await agents.register_agent(client, agent, steps=[])
            print(f"  + Agent registered: {AGENT_NAME}")
        except Exception as e:
            print(f"  ~ Agent may already exist: {e}")

        # =====================================================================
        # 2. Create Controls
        # =====================================================================
        print("\nCreating controls...")
        control_ids: list[tuple[int, str]] = []

        # ------------------------------------------------------------------
        # INTAKE STAGE: JSON evaluator - require topic, audience, content_type
        # ------------------------------------------------------------------
        intake_validation = {
            "description": "Validate content request has required fields (topic, audience, content_type)",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["validate_request"],
                "stages": ["pre"],
            },
            "condition": {
                "selector": {
                    "path": "input.request",
                },
                "evaluator": {
                    "name": "json",
                    "config": {
                        "required_fields": ["topic", "audience", "content_type"],
                    },
                },
            },
            "action": {"decision": "deny"},
        }
        cid = await create_control_safe(client, "flow-intake-validation", intake_validation)
        control_ids.append((cid, "flow-intake-validation"))

        # ------------------------------------------------------------------
        # RESEARCH STAGE: LIST evaluator - block banned sources
        # ------------------------------------------------------------------
        banned_sources = {
            "description": "Block research that references banned or unreliable sources",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["research_topic"],
                "stages": ["post"],
            },
            "condition": {
                "selector": {
                    "path": "output",
                },
                "evaluator": {
                    "name": "list",
                    "config": {
                        "values": [
                            "infowars.com",
                            "naturalcures.com",
                            "conspiracydaily.net",
                            "fakenews.org",
                            "unverifiedsource.com",
                        ],
                        "logic": "any",
                        "match_mode": "contains",
                        "case_sensitive": False,
                    },
                },
            },
            "action": {"decision": "deny"},
        }
        cid = await create_control_safe(client, "flow-research-banned-sources", banned_sources)
        control_ids.append((cid, "flow-research-banned-sources"))

        # ------------------------------------------------------------------
        # FACT-CHECK STAGE: REGEX evaluator - flag unverified claims/URLs
        # ------------------------------------------------------------------
        unverified_claims = {
            "description": "Flag fact-check results that contain unverified claim markers",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["fact_check"],
                "stages": ["post"],
            },
            "condition": {
                "selector": {
                    "path": "output",
                },
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": (
                            r"(?i)"
                            r"(?:UNVERIFIED|UNCONFIRMED|DEBUNKED|RETRACTED|FABRICATED)"
                            r"|(?:no\s+credible\s+source)"
                            r"|(?:cannot\s+be\s+verified)"
                        ),
                    },
                },
            },
            "action": {"decision": "deny"},
        }
        cid = await create_control_safe(client, "flow-factcheck-unverified", unverified_claims)
        control_ids.append((cid, "flow-factcheck-unverified"))

        # ------------------------------------------------------------------
        # DRAFT STAGE: REGEX evaluator - block PII in draft content
        # ------------------------------------------------------------------
        draft_pii = {
            "description": "Block drafts containing PII (SSN, email, phone)",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["write_draft"],
                "stages": ["post"],
            },
            "condition": {
                "selector": {
                    "path": "output",
                },
                "evaluator": {
                    "name": "regex",
                    "config": {
                        "pattern": (
                            r"(?:"
                            r"\b\d{3}-\d{2}-\d{4}\b"               # SSN
                            r"|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"  # Email
                            r"|\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"      # Phone
                            r")"
                        ),
