"""
CrewAI Financial Agent with Steering, Deny, and Observe actions.

Demonstrates the three key Agent Control action types in a realistic
wire-transfer scenario using a CrewAI crew:

  DENY  - Sanctioned country or fraud score blocks the transfer immediately.
  STEER - Large transfers pause execution and guide the agent through
          2FA verification or manager approval before retrying.
  OBSERVE - New recipients and PII in output are recorded for audit
            without blocking the transfer.

PREREQUISITE:
    Run setup_controls.py first:

        $ uv run --active python setup_controls.py

    Then run this example:

        $ uv run --active steering_financial_agent

Scenarios:
    1. Small legitimate transfer     -> OBSERVE (new recipient)
    2. Sanctioned country            -> DENY  (hard block)
    3. Large transfer ($15k)         -> STEER (2FA required, then allowed)
    4. Very large transfer ($75k)    -> STEER (manager approval, then allowed)
    5. High fraud score              -> DENY  (hard block)
"""

import json
import os

import agent_control

# ── Configuration ───────────────────────────────────────────────────────
AGENT_NAME = "crewai-financial-agent"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")

agent_control.init(
    agent_name=AGENT_NAME,
    agent_description="CrewAI financial agent with steering controls",
    server_url=SERVER_URL,
)


# ── Crew factory ────────────────────────────────────────────────────────

def create_financial_crew():
    from steering_financial_agent.crew import SteeringFinancialCrew

    return SteeringFinancialCrew().crew()


# ── Server check ────────────────────────────────────────────────────────

def verify_server():
    """Check that Agent Control server is reachable and controls exist."""
    import httpx

    try:
        r = httpx.get(f"{SERVER_URL}/api/v1/controls?limit=100", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        names = [c["name"] for c in data.get("controls", [])]
        required = [
            "deny-sanctioned-countries",
            "deny-high-fraud-score",
            "steer-require-2fa",
            "steer-require-manager-approval",
            "observe-new-recipient",
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
        print("Start the server:  make server-run  (from repo root)")
        return False


# ── Scenario runner ─────────────────────────────────────────────────────

def run_scenario(crew, number, title, request, expected):
    """Run a single scenario and print results."""
    print(f"\n{'#' * 60}")
    print(f"  SCENARIO {number}: {title}")
    print(f"{'#' * 60}")
    print(f"  Request:  {json.dumps(request)}")
    print(f"  Expected: {expected}")

    result = crew.kickoff(inputs={"transfer_request": json.dumps(request)})

    print(f"\n  Result: {str(result)[:300]}")
    print(f"{'#' * 60}\n")
    return result


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  CrewAI Financial Agent")
    print("  Steering, Deny & Observe with Agent Control")
    print("=" * 60)
    print()

    if not verify_server():
        return

    if not os.getenv("OPENAI_API_KEY"):
        print("\nSet OPENAI_API_KEY to run this example.")
