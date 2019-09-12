"""Tests for template-backed control API flows."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy

from agent_control_models import EvaluationRequest, Step
from fastapi.testclient import TestClient
from sqlalchemy import text

from .conftest import engine


def _template_payload() -> dict[str, object]:
    return {
        "template": {
            "description": "Regex denial template",
            "parameters": {
                "pattern": {
                    "type": "regex_re2",
                    "label": "Pattern",
                },
                "step_name": {
                    "type": "string",
                    "label": "Step Name",
                    "required": False,
                    "default": "templated-step",
                },
            },
            "definition_template": {
                "description": "Template-backed control",
                "execution": "server",
                "scope": {
                    "step_names": [{"$param": "step_name"}],
                    "stages": ["pre"],
                },
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "regex",
                        "config": {"pattern": {"$param": "pattern"}},
                    },
                },
                "action": {"decision": "deny"},
                "tags": ["template"],
            },
        },
        "template_values": {"pattern": "hello"},
    }


def _defaults_only_template_payload() -> dict[str, object]:
    return {
        "template": {
            "description": "List evaluator template",
            "parameters": {
                "values": {
                    "type": "string_list",
                    "label": "Values",
                    "default": ["secret", "blocked"],
                },
                "logic": {
                    "type": "enum",
                    "label": "Logic",
                    "allowed_values": ["any", "all"],
                    "default": "any",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "label": "Case Sensitive",
                    "default": False,
                },
            },
            "definition_template": {
                "description": "Defaulted list control",
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "list",
                        "config": {
                            "values": {"$param": "values"},
                            "logic": {"$param": "logic"},
                            "case_sensitive": {"$param": "case_sensitive"},
                        },
                    },
                },
                "action": {"decision": "deny"},
            },
        }
    }


def _case_sensitive_template_payload(
    *,
    values: list[str] | None = None,
    case_sensitive: bool | None = None,
    action: str = "deny",
) -> dict[str, object]:
    template_values: dict[str, object] = {}
    if values is not None:
        template_values["values"] = values
    if case_sensitive is not None:
        template_values["case_sensitive"] = case_sensitive

    return {
        "template": {
            "description": "Case sensitivity template",
            "parameters": {
                "values": {
                    "type": "string_list",
                    "label": "Values",
                    "required": False,
                    "default": ["HELLO"],
                },
                "case_sensitive": {
                    "type": "boolean",
                    "label": "Case Sensitive",
                    "required": False,
                    "default": True,
                },
            },
            "definition_template": {
                "description": "Case sensitivity control",
                "execution": "server",
                "scope": {
                    "step_names": ["templated-step"],
                    "stages": ["pre"],
                },
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "list",
                        "config": {
                            "values": {"$param": "values"},
                            "match_mode": "exact",
                            "case_sensitive": {"$param": "case_sensitive"},
                        },
                    },
                },
                "action": {"decision": action},
            },
        },
        "template_values": template_values,
    }


def _raw_control_payload(pattern: str = "raw", *, action: str = "deny") -> dict[str, object]:
    return {
        "description": "Raw control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "condition": {
            "selector": {"path": "input"},
            "evaluator": {
                "name": "regex",
                "config": {"pattern": pattern},
            },
        },
        "action": {"decision": action},
    }


def _nested_template_value(depth: int) -> object:
    value: object = "leaf"
    for _ in range(depth):
        value = {"nested": value}
    return value


def _create_template_control(client: TestClient) -> int:
    control_id, _ = _create_template_control_with_name(client)
    return control_id


def _create_template_control_with_name(
    client: TestClient,
    payload: dict[str, object] | None = None,
    *,
    name_prefix: str = "template-control",
) -> tuple[int, str]:
    control_name = f"{name_prefix}-{uuid.uuid4()}"
    response = client.put(
        "/api/v1/controls",
        json={
            "name": control_name,
            "data": payload or _template_payload(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["control_id"], control_name


def _assign_control_to_agent(
    client: TestClient,
    control_id: int,
    *,
    agent_name: str | None = None,
    via_policy: bool = True,
) -> str:
    effective_agent_name = agent_name or f"template-agent-{uuid.uuid4().hex[:12]}"
    init_response = client.post(
        "/api/v1/agents/initAgent",
        json={"agent": {"agent_name": effective_agent_name}, "steps": []},
    )
    assert init_response.status_code == 200, init_response.text

    if via_policy:
        policy_response = client.put("/api/v1/policies", json={"name": f"policy-{uuid.uuid4()}"})
        assert policy_response.status_code == 200, policy_response.text
        policy_id = policy_response.json()["policy_id"]

        add_control_response = client.post(
            f"/api/v1/policies/{policy_id}/controls/{control_id}"
        )
        assert add_control_response.status_code == 200, add_control_response.text

        assign_response = client.post(
            f"/api/v1/agents/{effective_agent_name}/policy/{policy_id}"
        )
        assert assign_response.status_code == 200, assign_response.text
    else:
        assign_response = client.post(
            f"/api/v1/agents/{effective_agent_name}/controls/{control_id}"
        )
        assert assign_response.status_code == 200, assign_response.text

    return effective_agent_name


def _create_raw_control(client: TestClient) -> int:
    response = client.put(
        "/api/v1/controls",
        json={
            "name": f"raw-control-{uuid.uuid4()}",
            "data": _raw_control_payload(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["control_id"]


def _evaluate_step(
    client: TestClient,
    agent_name: str,
    *,
    step_name: str,
    input_value: str,
    step_type: str = "llm",
    stage: str = "pre",
):
    request = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type=step_type, name=step_name, input=input_value, output=None),
        stage=stage,
    )
    return client.post("/api/v1/evaluation", json=request.model_dump(mode="json"))


def test_render_control_template_preview_returns_rendered_control(client: TestClient) -> None:
    # Given: a valid template-backed control payload
    # When: rendering a template preview through the public API
    response = client.post("/api/v1/control-templates/render", json=_template_payload())

    # Then: the rendered control includes resolved template metadata and values
    assert response.status_code == 200, response.text
    control = response.json()["control"]
    assert control["enabled"] is True
    assert control["template"]["description"] == "Regex denial template"
    assert control["template_values"] == {
        "pattern": "hello",
        "step_name": "templated-step",
    }
    assert control["condition"]["evaluator"]["config"]["pattern"] == "hello"
    assert control["scope"]["step_names"] == ["templated-step"]


def test_render_control_template_preview_uses_defaults_when_values_omitted(
    client: TestClient,
) -> None:
    # Given: a template whose defaults fully satisfy all parameters
    # When: rendering a template preview without explicit template values
    response = client.post(
        "/api/v1/control-templates/render",
        json=_defaults_only_template_payload(),
    )

    # Then: the rendered control uses the parameter defaults
    assert response.status_code == 200, response.text
    control = response.json()["control"]
    assert control["template_values"] == {
        "values": ["secret", "blocked"],
        "logic": "any",
        "case_sensitive": False,
    }
    assert control["condition"]["evaluator"]["name"] == "list"
    assert control["condition"]["evaluator"]["config"] == {
        "values": ["secret", "blocked"],
        "logic": "any",
        "case_sensitive": False,
    }


def test_render_control_template_preview_rejects_excessive_definition_nesting(
    client: TestClient,
) -> None:
    # Given: a template definition that exceeds the nesting limit
    payload = _template_payload()
    payload["template"]["definition_template"] = _nested_template_value(12)

    # When: rendering a template preview
    response = client.post("/api/v1/control-templates/render", json=payload)

    # Then: the API rejects the request with a clear validation error
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"].startswith("Request validation failed")
    assert "definition_template nesting depth exceeds maximum" in body["errors"][0]["message"]


def test_render_control_template_preview_rejects_excessive_definition_size(
    client: TestClient,
) -> None:
    # Given: a template definition that exceeds the size limit
    payload = _template_payload()
    payload["template"]["definition_template"] = list(range(1001))

    # When: rendering a template preview
    response = client.post("/api/v1/control-templates/render", json=payload)

    # Then: the API rejects the oversized template definition
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"].startswith("Request validation failed")
    assert "definition_template size exceeds maximum" in body["errors"][0]["message"]


def test_create_template_backed_control_persists_template_metadata(client: TestClient) -> None:
    # Given: a valid template-backed control created through the API
    control_id = _create_template_control(client)

    # When: fetching the stored control data
    response = client.get(f"/api/v1/controls/{control_id}/data")

    # Then: both template metadata and rendered values are persisted
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["template"]["description"] == "Regex denial template"
    assert data["template_values"] == {
        "pattern": "hello",
        "step_name": "templated-step",
    }
    assert data["condition"]["evaluator"]["config"]["pattern"] == "hello"
    assert data["scope"]["step_names"] == ["templated-step"]


def test_get_control_returns_template_metadata_for_template_backed_control(
    client: TestClient,
) -> None:
    # Given: a template-backed control created through the API
    control_id, control_name = _create_template_control_with_name(client)

    # When: fetching the full control resource
    response = client.get(f"/api/v1/controls/{control_id}")

    # Then: the response includes template metadata alongside normal control metadata
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == control_id
    assert body["name"] == control_name
    assert body["data"]["template"]["description"] == "Regex denial template"
    assert body["data"]["template_values"] == {
        "pattern": "hello",
        "step_name": "templated-step",
    }


def test_create_template_backed_control_persists_resolved_defaults_when_values_omitted(
    client: TestClient,
) -> None:
    # Given: a template-backed control created without explicit template values
    control_id, _ = _create_template_control_with_name(
        client,
        _defaults_only_template_payload(),
        name_prefix="defaulted-template-control",
    )

    # When: fetching the stored control data
    response = client.get(f"/api/v1/controls/{control_id}/data")

    # Then: the persisted template values and rendered config include resolved defaults
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["template_values"] == {
        "values": ["secret", "blocked"],
        "logic": "any",
        "case_sensitive": False,
