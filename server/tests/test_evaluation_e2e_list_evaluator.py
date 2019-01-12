"""End-to-end tests for AllowList/DenyList logic using the new ListEvaluator."""
import uuid
from fastapi.testclient import TestClient
from agent_control_models import EvaluationRequest, Step
from .utils import create_and_assign_policy

def test_list_evaluator_denylist_behavior(client: TestClient):
    """Test DenyList behavior: Block if ANY value matches."""
    # Given: A registered agent with a DenyList control blocking "rm" and "shutdown"
    control_data = {
        "description": "DenyList Control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.cmd"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["rm", "shutdown"],
                "logic": "any",
                "match_on": "match" # Triggers (returns True) if any match found
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(client, control_data, agent_name="DenyListAgent")

    # Case 1: Safe Value
    # When: Sending a tool step with a safe command "ls"
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="shell", input={"cmd": "ls"}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))

    # Then: The request should be allowed (is_safe=True)
    assert resp.json()["is_safe"] is True

    # Case 2: Unsafe Value
    # When: Sending a tool step with a forbidden command "rm"
    req_unsafe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="shell", input={"cmd": "rm"}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_unsafe.model_dump(mode="json"))

    # Then: The request should be denied (is_safe=False) and match the control
    assert resp.json()["is_safe"] is False
    assert resp.json()["matches"][0]["control_name"] == control_name


def test_list_evaluator_allowlist_behavior(client: TestClient):
    """Test AllowList behavior: Block if value is NOT in list."""
    # Given: A registered agent with an AllowList control allowing ONLY "safe_tool"
    # We use match_on="no_match" to trigger the control (Deny) if the value is NOT found in the list
    control_data = {
        "description": "AllowList Control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "name"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["safe_tool"],
                "logic": "any", 
                "match_on": "no_match" # Triggers if NO match found
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(client, control_data, agent_name="AllowListAgent")

    # Case 1: Allowed Value
    # When: Sending a tool step with the allowed tool "safe_tool"
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="safe_tool", input={}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))

    # Then: The request should be allowed
    assert resp.json()["is_safe"] is True

    # Case 2: Disallowed Value
    # When: Sending a tool step with a tool NOT in the list ("unknown_tool")
    req_unsafe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="unknown_tool", input={}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_unsafe.model_dump(mode="json"))

    # Then: The request should be denied
    assert resp.json()["is_safe"] is False
    assert resp.json()["matches"][0]["control_name"] == control_name


def test_list_evaluator_case_insensitive(client: TestClient):
    """Test case-insensitive matching."""
    # Given: A control blocking "BlockMe" with case_sensitive=False
    control_data = {
        "description": "Case Insensitive Control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["BlockMe"],
                "case_sensitive": False,
                "match_on": "match"
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(client, control_data, agent_name="CaseAgent")

    # When: Sending input "blockme" (lowercase)
    req = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="llm", name="test-step", input="blockme", output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req.model_dump(mode="json"))

    # Then: The request should be denied because it matches case-insensitively
    assert resp.json()["is_safe"] is False


def test_list_evaluator_list_input_any_match(client: TestClient):
    """Test matching against a list input (e.g. tags) with logic='any'."""
    # Given: A control blocking request if ANY tag is "restricted"
    control_data = {
        "description": "Restricted Tags",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.tags"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["restricted"],
                "logic": "any",
                "match_on": "match"
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, _ = create_and_assign_policy(client, control_data, agent_name="TagAgent")

    # Case 1: List containing restricted item
    # When: Sending tags ["public", "restricted"]
    req_unsafe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="update", input={"tags": ["public", "restricted"]}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_unsafe.model_dump(mode="json"))

    # Then: The request should be denied
    assert resp.json()["is_safe"] is False

    # Case 2: List containing only safe items
    # When: Sending tags ["public", "internal"]
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="update", input={"tags": ["public", "internal"]}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))

    # Then: The request should be allowed
    assert resp.json()["is_safe"] is True


def test_list_evaluator_list_input_all_match(client: TestClient):
    """Test matching against a list input with logic='all'."""
    # Given: A control requiring ALL tags to be "safe_tag" or "audit_approved"
    # We trigger Deny if the condition (ALL items match) is NOT met (match_on="no_match")
    control_data = {
        "description": "Enforce Safe Tags",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.tags"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["safe_tag", "audit_approved"],
                "logic": "all",
                "match_on": "no_match" # Trigger if logic 'all' fails
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, _ = create_and_assign_policy(client, control_data, agent_name="SafeTagAgent")

    # Case 1: All items match
    # When: Sending only safe tags
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="update", input={"tags": ["safe_tag", "audit_approved"]}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))

    # Then: The request should be allowed (logic=True, match_on="no_match" -> Trigger=False)
    assert resp.json()["is_safe"] is True

    # Case 2: Mixed items (one unsafe)
    # When: Sending tags with one risky item
    req_unsafe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="update", input={"tags": ["safe_tag", "risky"]}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_unsafe.model_dump(mode="json"))

    # Then: The request should be denied (logic=False, match_on="no_match" -> Trigger=True)
    assert resp.json()["is_safe"] is False


def test_list_evaluator_disallow_name(client: TestClient):
    """Test Disallowing specific tool names (DenyList on name)."""
    # Given: A control blocking "delete_user" and "drop_db" tools
    control_data = {
        "description": "Block Dangerous Tools",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "name"},
        "evaluator": {
            "name": "list",
            "config": {
                "values": ["delete_user", "drop_db"],
                "logic": "any",
                "match_on": "match" # Trigger if name is in list
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(client, control_data, agent_name="NoDangerousTools")

    # Case 1: Allowed Tool
    # When: Calling a safe tool
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="get_user", input={"id": "123"}, output=None),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.json()["is_safe"] is True

    # Case 2: Disallowed Tool
    # When: Calling a dangerous tool
    req_unsafe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", name="delete_user", input={"id": "123"}, output=None),
