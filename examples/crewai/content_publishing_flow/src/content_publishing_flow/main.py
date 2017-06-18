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
                "Research",
                topic=self.state.topic,
                audience=self.state.audience,
            )
        except (ControlViolationError, RuntimeError) as e:
            self.state.status = "blocked"
            self.state.error = f"Research blocked: {e}"
            return

        # Step 2: Fact-check
        try:
            fact_check_output = await run_controlled_async(
                controlled_fact_check,
                "Fact-Check",
                research_text=research_output,
            )
        except (ControlViolationError, RuntimeError) as e:
            self.state.status = "blocked"
            self.state.error = f"Fact-check blocked: {e}"
            return

        self.state.research = research_output
        print(f"\n  Research complete ({len(research_output)} chars)")
        print(f"  Fact-check: PASSED")

    # -----------------------------------------------------------------------
    # @listen(research): draft_content
    # -----------------------------------------------------------------------
    @listen(research)
    async def draft_content(self):
        """Write the content draft."""
        print("\n" + "=" * 60)
        print("STAGE: draft_content")
        print("=" * 60)

        if self.state.status in ("blocked", "failed"):
            print("  Skipping draft - pipeline already failed.")
            return

        try:
            draft = await run_controlled_async(
                controlled_write_draft,
                "Draft Writer",
                topic=self.state.topic,
                audience=self.state.audience,
                content_type=self.state.content_type,
                research=self.state.research,
            )
            self.state.draft = draft
            print(f"  Draft written ({len(draft)} chars)")
            print(f"  Content type: {self.state.content_type}")

        except ControlViolationError as e:
            self.state.status = "blocked"
            self.state.error = f"Draft blocked: {e.message}"
            print(f"  Draft BLOCKED: {e.message}")

    # -----------------------------------------------------------------------
    # @router(draft_content): quality_gate
    # -----------------------------------------------------------------------
    @router(draft_content)
    async def quality_gate(self):
        """Route based on content_type and pipeline status."""
        print("\n" + "=" * 60)
        print("STAGE: quality_gate (router)")
        print("=" * 60)

        if self.state.status in ("blocked", "failed"):
            print(f"  Routing: pipeline_end (status={self.state.status})")
            return "pipeline_end"

        content_type = self.state.content_type
        if content_type == "blog_post":
            print(f"  Routing: low_risk (blog_post -> auto-publish)")
            return "low_risk"
        elif content_type == "press_release":
            print(f"  Routing: high_risk (press_release -> compliance review)")
            return "high_risk"
        else:
            print(f"  Routing: escalation (internal_memo -> human review)")
            return "escalation"

    # -----------------------------------------------------------------------
    # @listen("low_risk"): auto_publish
    # -----------------------------------------------------------------------
    @listen("low_risk")
    async def auto_publish(self):
        """Auto-publish with a final PII scan."""
        print("\n" + "=" * 60)
        print("STAGE: auto_publish (low_risk path)")
        print("=" * 60)

        try:
            result = await run_controlled_async(
                controlled_publish,
                "Publish (PII Scan)",
                content=self.state.draft,
                content_type=self.state.content_type,
            )
            self.state.final_content = self.state.draft
            self.state.status = "published"
            parsed = json.loads(result)
            print(f"  Published at: {parsed.get('timestamp')}")
            print(f"  Status: {parsed.get('status')}")

        except ControlViolationError as e:
            self.state.status = "blocked"
            self.state.error = f"Publish blocked (PII detected): {e.message}"
            print(f"  Publish BLOCKED: {e.message}")

    # -----------------------------------------------------------------------
    # @listen("high_risk"): compliance_review
    # -----------------------------------------------------------------------
    @listen("high_risk")
    async def compliance_review(self):
        """Compliance review with Legal Reviewer + Editor (simulated crew)."""
        print("\n" + "=" * 60)
        print("STAGE: compliance_review (high_risk path)")
        print("=" * 60)
        print("  Running compliance crew: Legal Reviewer + Editor")

        # Step 1: Legal review
        try:
            legal_result = await run_controlled_async(
                controlled_legal_review,
                "Legal Review",
                content=self.state.draft,
            )
            legal_data = json.loads(legal_result)
            print(f"  Legal reviewed: {legal_data.get('legal_reviewed')}")
            print(f"  Disclaimer: {legal_data.get('disclaimer', '')[:60]}...")
        except ControlViolationError as e:
            self.state.status = "blocked"
            self.state.error = f"Legal review blocked: {e.message}"
            print(f"  Legal review BLOCKED: {e.message}")
            return

        # Step 2: Edit content
        # Client-side check: press releases require an Executive Summary.
        # First pass without it, detect the absence, then retry with it.
        include_exec_summary = False
        max_attempts = 2

        for attempt in range(1, max_attempts + 1):
            try:
                edited = await run_controlled_async(
                    controlled_edit_content,
                    f"Editor (attempt {attempt})",
                    content=self.state.draft,
                    include_executive_summary=include_exec_summary,
                )

                # Client-side steering: check for Executive Summary in press releases
                if (
                    self.state.content_type == "press_release"
                    and "Executive Summary" not in edited
                    and not include_exec_summary
                ):
                    print(f"  [Editor] STEERED (client-side): missing Executive Summary")
                    print(f"  Correction: will add Executive Summary on next attempt")
                    include_exec_summary = True
                    continue

                # Publish
                try:
                    result = await run_controlled_async(
                        controlled_publish,
                        "Publish (after compliance)",
                        content=edited,
                        content_type=self.state.content_type,
                    )
                    self.state.final_content = edited
                    self.state.status = "published"
                    parsed = json.loads(result)
                    print(f"\n  Published at: {parsed.get('timestamp')}")
                    print(f"  Status: {parsed.get('status')}")
                    return

                except ControlViolationError as e:
                    self.state.status = "blocked"
                    self.state.error = f"Final publish blocked: {e.message}"
                    return

            except ControlViolationError as e:
                self.state.status = "blocked"
                self.state.error = f"Editor blocked: {e.message}"
                return

        self.state.status = "failed"
        self.state.error = "Editor failed after max retries"
        print(f"  Editor: exhausted {max_attempts} attempts")

    # -----------------------------------------------------------------------
    # @listen("escalation"): human_review
    # -----------------------------------------------------------------------
    @listen("escalation")
    async def human_review(self):
        """Submit for human review. STEER control pauses for manager approval."""
        print("\n" + "=" * 60)
        print("STAGE: human_review (escalation path)")
        print("=" * 60)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                result = await run_controlled_async(
                    controlled_human_review,
                    f"Human Review (attempt {attempt})",
                    content=self.state.draft,
                    content_type=self.state.content_type,
                )
                # If we get here without steer, it was approved
                self.state.final_content = self.state.draft
                self.state.status = "pending_review"
                print(f"  Submitted for review successfully")
                return

            except ControlSteerError as e:
                print(f"  Flow paused - manager approval required")
                try:
                    guidance = json.loads(e.steering_context)
                    print(f"  Reason: {guidance.get('reason', 'Approval required')}")
                    print(f"  Required: {guidance.get('required_actions', [])}")
                except (json.JSONDecodeError, AttributeError):
                    print(f"  Steering context: {e.steering_context}")

                # In a real system, this would pause and wait for async approval.
                # For demo purposes, we show the steering and mark as pending.
                self.state.status = "pending_approval"
                self.state.error = (
                    f"Awaiting manager approval. "
                    f"Steering context: {e.steering_context}"
                )
                return

            except ControlViolationError as e:
                self.state.status = "blocked"
                self.state.error = f"Human review blocked: {e.message}"
                return

    # -----------------------------------------------------------------------
    # @listen("pipeline_end"): handle_pipeline_end
    # -----------------------------------------------------------------------
    @listen("pipeline_end")
    def handle_pipeline_end(self):
        """Handle cases where the pipeline was blocked or failed before routing."""
        print("\n" + "=" * 60)
        print("STAGE: pipeline_end")
        print("=" * 60)
        print(f"  Status: {self.state.status}")
        print(f"  Error: {self.state.error}")



# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def print_banner(title: str):
    """Print a scenario banner."""
    width = 70
    print("\n" + "#" * width)
    print(f"# {title}")
    print("#" * width)


def print_result(state: PublishingState):
    """Print the final state of a flow run."""
    print("\n  --- Flow Result ---")
    print(f"  Status:       {state.status}")
    if state.error:
        print(f"  Error:        {state.error}")
    if state.final_content:
        preview = state.final_content[:150].replace("\n", " ")
        print(f"  Content:      {preview}...")
    print(f"  Content Type: {state.content_type}")
    print()


def run_flow_scenario(
    title: str,
    topic: str,
    audience: str,
    content_type: str,
) -> PublishingState:
    """Run the full flow with given inputs and return the final state."""
    print_banner(title)

    flow = ContentPublishingFlow()
    flow._state = PublishingState(
        topic=topic,
        audience=audience,
        content_type=content_type,
    )

    # kickoff() runs the flow synchronously
    flow.kickoff()

    print_result(flow.state)
    return flow.state


def run_direct_tool_scenario(
    title: str,
    tool_label: str,
    controlled_fn,
    kwargs: dict,
) -> str | None:
    """Run a single controlled tool call to demonstrate blocking."""
    print_banner(title)

    try:
        result = run_controlled_sync(controlled_fn, tool_label, **kwargs)
        print(f"\n  --- Result ---")
        print(f"  Status: PASSED")
        preview = str(result)[:200].replace("\n", " ")
        print(f"  Output: {preview}...")
        print()
        return result
    except ControlViolationError as e:
        print(f"\n  --- Result ---")
        print(f"  Status: BLOCKED")
        print(f"  Control: {e.control_name}")
        print(f"  Reason: {e.message}")
        print()
        return None
    except ControlSteerError as e:
        print(f"\n  --- Result ---")
        print(f"  Status: STEERED")
        print(f"  Control: {e.control_name}")
        print(f"  Steering: {e.steering_context}")
        print()
        return None
    except RuntimeError as e:
        print(f"\n  --- Result ---")
        print(f"  Status: ERROR")
        print(f"  Error: {e}")
        print()
        return None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_setup() -> bool:
    """Verify the Agent Control server is running and controls are configured."""
    import httpx

    try:
        print("Verifying Agent Control server...")
        response = httpx.get(f"{SERVER_URL}/api/v1/controls?limit=100", timeout=5.0)
        response.raise_for_status()

        data = response.json()
        all_controls = [c["name"] for c in data.get("controls", [])]

        required = [
            "flow-intake-validation",
            "flow-research-banned-sources",
            "flow-draft-pii-block",
            "flow-draft-banned-topics",
            "flow-publish-pii-scan",
        ]

        missing = [c for c in required if c not in all_controls]
        if missing:
            print(f"  Missing controls: {missing}")
            print("  Run: uv run --active python setup_controls.py")
            return False

        print(f"  Server: {SERVER_URL}")
        print(f"  Controls found: {len(all_controls)}")
        return True

    except httpx.ConnectError:
        print(f"  Cannot connect to server at {SERVER_URL}")
        print("  Start the server: make server-run")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
