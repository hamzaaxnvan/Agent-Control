"""Tests for local control execution in SDK.

These tests verify the check_evaluation_with_local function:
1. Local-only controls execute locally without server call
2. Server-only controls call server
3. Mixed controls: local first, then server
4. Deny short-circuit: local deny skips server call
5. Result merging: combines matches/errors from both
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agent_control.client import AgentControlClient
from agent_control.evaluation import (
    _merge_results,
    check_evaluation_with_local,
)
from agent_control_models import (
    ControlMatch,
    EvaluationResponse,
    EvaluatorResult,
    Step,
)

# =============================================================================
# Test Fixtures
# =============================================================================


class _RuntimeAuthDuckClient:
    """Minimal custom client that exposes the runtime-auth evaluation method."""

    base_url = "https://agent-control.test"

    def __init__(self) -> None:
        self.runtime_requests: list[dict[str, Any]] = []
        self.response = MagicMock()
        self.response.json.return_value = {"is_safe": True, "confidence": 1.0}
        self.response.raise_for_status = MagicMock()

    async def post_runtime_evaluation(
        self,
        *,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> MagicMock:
        self.runtime_requests.append(
            {
                "json": json,
                "headers": headers,
                "target_type": target_type,
                "target_id": target_id,
            }
        )
        return self.response


class _HttpOnlyDuckClient:
    """Minimal custom client that exposes the normal HTTP evaluation path."""

    base_url = "https://agent-control.test"

    def __init__(self) -> None:
        self.response = MagicMock()
        self.response.json.return_value = {"is_safe": True, "confidence": 1.0}
        self.response.raise_for_status = MagicMock()
        self.http_client = MagicMock()
        self.http_client.post = AsyncMock(return_value=self.response)


@pytest.fixture
def agent_name() -> str:
    """Test agent name."""
    return "agent-000000000001"


@pytest.fixture
def llm_payload() -> Step:
    """Sample LLM call payload."""
    return Step(type="llm", name="test-step", input="test input", output=None)


@pytest.fixture
def tool_payload() -> Step:
    """Sample tool step payload."""
    return Step(type="tool", name="test_tool", input={"query": "test"}, output=None)


def make_control_dict(
    control_id: int,
    name: str,
    *,
    enabled: bool = True,
    execution: str = "server",
    evaluator: str = "regex",
    pattern: str = r"test",
    action: str = "deny",
    step_type: str = "llm",
    stage: str = "pre",
    step_names: list[str] | None = None,
    step_name_regex: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Create a control dict like what initAgent returns."""
    # Default path based on payload type
    if path is None:
        path = "input"

    scope: dict[str, Any] = {"step_types": [step_type], "stages": [stage]}
    if step_names is not None:
        scope["step_names"] = step_names
    if step_name_regex is not None:
        scope["step_name_regex"] = step_name_regex

    return {
        "id": control_id,
        "name": name,
        "control": {
            "description": f"Test control {name}",
            "enabled": enabled,
            "execution": execution,
            "scope": scope,
            "condition": {
                "selector": {"path": path},
                "evaluator": {
                    "name": evaluator,
                    "config": {"pattern": pattern},
                },
            },
            "action": {"decision": action},
        },
    }


def add_template_metadata(control: dict[str, Any], *, pattern: str = "test") -> dict[str, Any]:
    """Attach realistic template metadata to a cached control payload."""
    control["control"]["template"] = {
        "parameters": {
            "pattern": {
                "type": "regex_re2",
                "label": "Pattern",
            }
        },
        "definition_template": {
            "description": "Template-backed control",
            "execution": control["control"]["execution"],
            "scope": control["control"]["scope"],
            "condition": {
                "selector": {"path": "input"},
                "evaluator": {
                    "name": "regex",
                    "config": {"pattern": {"$param": "pattern"}},
                },
            },
            "action": control["control"]["action"],
        },
    }
    control["control"]["template_values"] = {"pattern": pattern}
    return control


def make_unrendered_template_control(
    control_id: int, name: str
) -> dict[str, Any]:
    """Build a cached control payload that represents an unrendered template."""
    return {
        "id": control_id,
        "name": name,
        "control": {
            "template": {
                "parameters": {
                    "pattern": {"type": "regex_re2", "label": "Pattern"},
                },
                "definition_template": {
                    "execution": "server",
                    "scope": {"step_types": ["llm"], "stages": ["pre"]},
                    "condition": {
                        "selector": {"path": "input"},
                        "evaluator": {
                            "name": "regex",
                            "config": {"pattern": {"$param": "pattern"}},
                        },
                    },
                    "action": {"decision": "deny"},
                },
            },
            "template_values": {},
            "enabled": False,
        },
    }


NON_APPLICABLE_CONTROL_CASES = [
    pytest.param({"enabled": False}, id="disabled"),
    pytest.param({"stage": "post"}, id="stage_mismatch"),
    pytest.param({"step_type": "tool"}, id="step_type_mismatch"),
    pytest.param({"step_names": ["send_email"]}, id="step_name_mismatch"),
    pytest.param({"step_name_regex": r"^send_.*$"}, id="step_name_regex_mismatch"),
]


# =============================================================================
# Test: _merge_results
# =============================================================================


class TestMergeResults:
    """Tests for result merging logic."""

    def test_merge_both_safe(self):
        """Merging two safe results should be safe."""
        local = EvaluationResponse(is_safe=True, confidence=0.9)
        server = EvaluationResponse(is_safe=True, confidence=0.8)

        result = _merge_results(local, server)

        assert result.is_safe is True
        assert result.confidence == 0.8  # min of both

    def test_merge_local_deny(self):
        """Local deny should make merged result unsafe."""
        local = EvaluationResponse(is_safe=False, confidence=1.0)
        server = EvaluationResponse(is_safe=True, confidence=0.9)

        result = _merge_results(local, server)

        assert result.is_safe is False
        assert result.confidence == 0.9  # min of both

    def test_merge_server_deny(self):
        """Server deny should make merged result unsafe."""
        local = EvaluationResponse(is_safe=True, confidence=0.9)
        server = EvaluationResponse(is_safe=False, confidence=1.0)

        result = _merge_results(local, server)

        assert result.is_safe is False
        assert result.confidence == 0.9  # min of both

    def test_merge_both_deny(self):
        """Both denying should make merged result unsafe."""
        local = EvaluationResponse(is_safe=False, confidence=1.0)
        server = EvaluationResponse(is_safe=False, confidence=1.0)

        result = _merge_results(local, server)

        assert result.is_safe is False
        assert result.confidence == 1.0

    def test_merge_combines_matches(self):
        """Matches from both should be combined."""
        local_match = ControlMatch(
            control_id=1,
            control_name="local_ctrl",
            action="deny",
            result=EvaluatorResult(matched=True, confidence=1.0),
        )
        server_match = ControlMatch(
            control_id=2,
            control_name="server_ctrl",
            action="deny",
            result=EvaluatorResult(matched=True, confidence=1.0),
        )
