"""End-to-end tests for evaluator error handling."""
import uuid
from unittest.mock import AsyncMock, MagicMock

from agent_control_models import (
    ControlMatch,
    EvaluationRequest,
    EvaluationResponse,
    EvaluatorResult,
    Step,
)
from agent_control_server.db import async_engine
from agent_control_server.endpoints.evaluation import (
    SAFE_EVALUATOR_ERROR,
    SAFE_EVALUATOR_TIMEOUT_ERROR,
    _sanitize_control_match,
)
from fastapi.testclient import TestClient

from .utils import create_and_assign_policy


def test_evaluation_with_agent_scoped_evaluator_missing(client: TestClient):
    """Test that referencing a missing agent evaluator fails during control creation.

    Given: A control referencing agent:evaluator that doesn't exist
    When: Creating the control
    Then: Returns 422 EVALUATOR_NOT_FOUND
    """
    # Given: an agent without evaluators
    agent_name = f"testagent-{uuid.uuid4().hex[:12]}"
    client.post("/api/v1/agents/initAgent", json={
        "agent": {
            "agent_name": agent_name
        },
        "steps": [],
        "evaluators": []
    })

    # And: a control referencing a non-existent agent evaluator
    control_data = {
        "description": "Test control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {
            "name": f"{agent_name}:missing-evaluator",
            "config": {}
        },
        "action": {"decision": "deny"}
    }

    # When: creating the control with a missing agent-scoped evaluator
    set_resp = client.put(
        "/api/v1/controls",
        json={"name": f"control-{uuid.uuid4().hex[:8]}", "data": control_data},
    )

    # Then: the missing evaluator is surfaced deterministically
    assert set_resp.status_code == 422
    assert set_resp.json()["error_code"] == "EVALUATOR_NOT_FOUND"


def test_evaluation_control_with_invalid_config_caught_early(client: TestClient):
    """Test that invalid evaluator config is caught at control creation.

    Given: A control with invalid config for an evaluator
    When: Setting control data
    Then: Returns 422 with validation error
    """
    # When: creating a control with invalid regex config (missing required 'pattern')
    control_data = {
        "description": "Test control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {
            "name": "regex",
            "config": {}  # Missing required 'pattern' field
        },
        "action": {"decision": "deny"}
    }

    set_resp = client.put(
        "/api/v1/controls",
        json={"name": f"control-{uuid.uuid4().hex[:8]}", "data": control_data},
    )

    # Then: a validation error is returned
    assert set_resp.status_code == 422
    assert "pattern" in set_resp.text.lower() or "required" in set_resp.text.lower()


def test_evaluation_errors_field_populated_on_evaluator_failure(
    client: TestClient, monkeypatch
):
    """Test that errors field is populated when evaluator fails at runtime.

    Given: A valid control with an evaluator that crashes during evaluation
    When: Evaluation is requested
    Then: Response has errors field populated and is_safe=False (for deny)
    """
    # Given: an agent with a working control
    control_data = {
        "description": "Test control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {
            "name": "regex",
            "config": {"pattern": "test"}
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(client, control_data)

    # And: an evaluator instance that throws during evaluation
    mock_evaluator = MagicMock()
    mock_evaluator.evaluate = AsyncMock(side_effect=RuntimeError("Simulated evaluator crash"))
    mock_evaluator.get_timeout_seconds = MagicMock(return_value=30.0)

    # Patch where it's used (in core module), not where it's defined
    import agent_control_engine.core as core_module

    def mock_get_evaluator_instance(config):
        return mock_evaluator

    monkeypatch.setattr(core_module, "get_evaluator_instance", mock_get_evaluator_instance)

    # When: sending an evaluation request
    payload = Step(type="llm", name="test-step", input="test content", output=None)
    req = EvaluationRequest(
        agent_name=agent_name,
        step=payload,
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req.model_dump(mode="json"))

    # Then: the response reports an evaluation error
    assert resp.status_code == 200
    data = resp.json()

    # Then: is_safe is false because deny control errored (fail closed)
    assert data["is_safe"] is False

    # And: confidence is zero (no successful evaluations)
    assert data["confidence"] == 0.0

    # And: errors field is populated with the failing control
    assert data["errors"] is not None
    assert len(data["errors"]) == 1
    assert data["errors"][0]["control_name"] == control_name
    assert (
        data["errors"][0]["result"]["error"]
        == "Evaluation failed due to an internal evaluator error."
    )
    assert "RuntimeError" not in data["errors"][0]["result"]["error"]
    assert "Simulated evaluator crash" not in data["errors"][0]["result"]["error"]
    condition_trace = data["errors"][0]["result"]["metadata"]["condition_trace"]
    assert condition_trace["error"] == SAFE_EVALUATOR_ERROR
    assert condition_trace["message"] == SAFE_EVALUATOR_ERROR
    assert "RuntimeError" not in condition_trace["error"]
    assert "Simulated evaluator crash" not in condition_trace["message"]

    # And: no matches are returned because evaluation failed
    assert data["matches"] is None or len(data["matches"]) == 0


def test_evaluation_response_is_sanitized_without_server_side_observability(
    client: TestClient,
    monkeypatch,
) -> None:
    """Evaluation stays pure and returns only sanitized semantics."""
    control_data = {
        "description": "Test control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {
            "name": "regex",
            "config": {"pattern": "test"}
        },
        "action": {"decision": "deny"}
    }
