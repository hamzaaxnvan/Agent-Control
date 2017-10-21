"""
Content Publishing Flow - CrewAI Flow with Agent Control Guardrails.

Demonstrates CrewAI Flows (routing, embedded crews, state management)
integrated with Agent Control at every pipeline stage.

Flow Architecture:
    @start: intake_request
        -> Validates and classifies the content request
        -> Control: JSON evaluator (require topic, audience, content_type)

    @listen(intake_request): research
        -> 2-agent crew: Researcher + Fact-Checker
        -> Controls: LIST (banned sources), REGEX (unverified claims)

    @listen(research): draft_content
        -> Single agent writes content
        -> Controls: REGEX (block PII), LIST (block banned topics)

    @router(draft_content): quality_gate
        -> Routes based on content_type:
            "blog_post"      -> "low_risk"   (auto-publish)
            "press_release"  -> "high_risk"  (compliance review)
            "internal_memo"  -> "escalation" (human review)

    @listen("low_risk"):   auto_publish     -> Final PII scan, then publish
    @listen("high_risk"):  compliance_review -> Legal + Editor crew
    @listen("escalation"): human_review     -> STEER for manager approval

PREREQUISITE:
    Run setup_controls.py first:
        $ uv run --active python setup_controls.py

    Then run this flow:
        $ uv run --active kickoff
"""

import asyncio
import json
import os
import sys

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

import agent_control
from agent_control import ControlSteerError, ControlViolationError, control

from content_publishing_flow.tools import (
    controlled_validate_request,
    controlled_research,
    controlled_fact_check,
    controlled_write_draft,
    controlled_legal_review,
    controlled_edit_content,
    controlled_publish,
    controlled_human_review,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGENT_NAME = "content-publishing-flow"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Flow State
# ---------------------------------------------------------------------------

class PublishingState(BaseModel):
    """Tracks data through the entire publishing pipeline."""

    topic: str = ""
    audience: str = ""
    content_type: str = ""  # "blog_post", "press_release", "internal_memo"
    research: str = ""
    draft: str = ""
    final_content: str = ""
    status: str = "pending"
    error: str = ""


# ---------------------------------------------------------------------------
# Helper: run a controlled function and handle errors
# ---------------------------------------------------------------------------

async def run_controlled_async(controlled_fn, label: str, **kwargs) -> str:
    """Run a controlled async function with error handling."""
    print(f"\n  [{label}] Evaluating controls...")
    try:
        result = await controlled_fn(**kwargs)
        print(f"  [{label}] Controls passed.")
        return result
    except ControlViolationError as e:
        print(f"  [{label}] BLOCKED by control '{e.control_name}': {e.message}")
        raise
    except ControlSteerError as e:
        print(f"  [{label}] STEERED by control '{e.control_name}': {e.message}")
        raise
    except RuntimeError as e:
        print(f"  [{label}] Control check failed: {e}")
        raise


def run_controlled_sync(controlled_fn, label: str, **kwargs) -> str:
    """Run a controlled async function synchronously (for use outside event loops)."""
    print(f"\n  [{label}] Evaluating controls...")
    try:
        result = asyncio.run(controlled_fn(**kwargs))
        print(f"  [{label}] Controls passed.")
        return result
    except ControlViolationError as e:
        print(f"  [{label}] BLOCKED by control '{e.control_name}': {e.message}")
        raise
    except ControlSteerError as e:
        print(f"  [{label}] STEERED by control '{e.control_name}': {e.message}")
        raise
    except RuntimeError as e:
        print(f"  [{label}] Control check failed: {e}")
        raise


# ---------------------------------------------------------------------------
# CrewAI Flow
# ---------------------------------------------------------------------------

class ContentPublishingFlow(Flow[PublishingState]):
    """
    Content publishing pipeline as a CrewAI Flow.

    Stages: intake -> research -> draft -> quality_gate
            -> auto_publish | compliance_review | human_review
    """

    # -----------------------------------------------------------------------
    # @start: intake_request
    # -----------------------------------------------------------------------
    @start()
    async def intake_request(self):
        """Validate and classify the incoming content request."""
        print("\n" + "=" * 60)
        print("STAGE: intake_request")
        print("=" * 60)

        request = {
            "topic": self.state.topic,
            "audience": self.state.audience,
            "content_type": self.state.content_type,
        }
        print(f"  Request: {json.dumps(request, indent=2)}")

        try:
            result = await run_controlled_async(
                controlled_validate_request,
                "Intake Validation",
                request=request,
            )
            parsed = json.loads(result)
            if not parsed.get("valid"):
                self.state.status = "failed"
                self.state.error = "Request missing required fields"
                print(f"  Result: INVALID - {self.state.error}")
                return "invalid"

            print(f"  Result: VALID - proceeding to research")
            return "valid"

        except ControlViolationError as e:
            self.state.status = "blocked"
            self.state.error = f"Intake blocked: {e.message}"
            print(f"  Result: BLOCKED at intake")
            return "blocked"

    # -----------------------------------------------------------------------
    # @listen(intake_request): research
    # -----------------------------------------------------------------------
    @listen(intake_request)
    async def research(self):
        """Run research and fact-checking (simulated 2-agent crew)."""
        print("\n" + "=" * 60)
        print("STAGE: research (Researcher + Fact-Checker)")
        print("=" * 60)

        if self.state.status in ("blocked", "failed"):
            print("  Skipping research - intake failed.")
            return

        # Step 1: Research
        try:
            research_output = await run_controlled_async(
                controlled_research,
