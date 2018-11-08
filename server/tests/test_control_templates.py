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
    }
    assert data["condition"]["evaluator"]["config"] == {
        "values": ["secret", "blocked"],
        "logic": "any",
        "case_sensitive": False,
    }


def test_create_template_backed_control_failure_does_not_persist_control(
    client: TestClient,
) -> None:
    # Given: an invalid template-backed create payload and the current control list
    invalid_payload = _template_payload()
    invalid_payload["template_values"] = {"pattern": "["}
    control_name = f"invalid-template-control-{uuid.uuid4()}"

    before_response = client.get("/api/v1/controls")
    assert before_response.status_code == 200, before_response.text
    before_controls = before_response.json()["controls"]
    before_ids = {control["id"] for control in before_controls}

    # When: creating the invalid template-backed control
    response = client.put(
        "/api/v1/controls",
        json={"name": control_name, "data": invalid_payload},
    )

    # Then: the request fails and no control is persisted
    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "TEMPLATE_PARAMETER_INVALID"

    after_response = client.get("/api/v1/controls")
    assert after_response.status_code == 200, after_response.text
    after_controls = after_response.json()["controls"]
    after_ids = {control["id"] for control in after_controls}
    assert after_ids == before_ids
    assert all(control["name"] != control_name for control in after_controls)


def test_template_backed_control_evaluates_after_policy_attachment(client: TestClient) -> None:
    # Given: a template-backed control attached to an agent through a policy
    control_id, control_name = _create_template_control_with_name(client)
    agent_name = _assign_control_to_agent(client, control_id)

    # When: evaluating a non-matching step and then a matching step
    safe_response = _evaluate_step(
        client,
        agent_name,
        step_name="other-step",
        input_value="hello",
    )
    assert safe_response.status_code == 200, safe_response.text
    assert safe_response.json()["is_safe"] is True

    deny_response = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    # Then: only the matching step is denied by the attached template-backed control
    assert deny_response.status_code == 200, deny_response.text
    body = deny_response.json()
    assert body["is_safe"] is False
    assert body["matches"][0]["control_name"] == control_name


def test_template_backed_control_can_be_disabled_and_reenabled_in_evaluation(
    client: TestClient,
) -> None:
    # Given: an attached template-backed control
    control_id, control_name = _create_template_control_with_name(client)
    agent_name = _assign_control_to_agent(client, control_id)

    # When: evaluating before disabling, after disabling, and after re-enabling the control
    initial_response = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    assert initial_response.status_code == 200, initial_response.text
    assert initial_response.json()["is_safe"] is False

    disable_response = client.patch(f"/api/v1/controls/{control_id}", json={"enabled": False})
    assert disable_response.status_code == 200, disable_response.text

    disabled_eval = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    assert disabled_eval.status_code == 200, disabled_eval.text
    assert disabled_eval.json()["is_safe"] is True

    enable_response = client.patch(f"/api/v1/controls/{control_id}", json={"enabled": True})
    assert enable_response.status_code == 200, enable_response.text

    reenabled_eval = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    # Then: evaluation reflects the user-managed enabled state
    assert reenabled_eval.status_code == 200, reenabled_eval.text
    body = reenabled_eval.json()
    assert body["is_safe"] is False
    assert body["matches"][0]["control_name"] == control_name


def test_template_backed_control_rename_is_reflected_in_evaluation(client: TestClient) -> None:
    # Given: an attached template-backed control
    control_id, _ = _create_template_control_with_name(client)
    agent_name = _assign_control_to_agent(client, control_id)
    renamed_control_name = f"renamed-template-control-{uuid.uuid4()}"

    # When: renaming the control and evaluating a matching step
    patch_response = client.patch(
        f"/api/v1/controls/{control_id}",
        json={"name": renamed_control_name},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["name"] == renamed_control_name

    eval_response = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )

    # Then: the evaluation match reflects the updated control name
    assert eval_response.status_code == 200, eval_response.text
    body = eval_response.json()
    assert body["is_safe"] is False
    assert body["matches"][0]["control_name"] == renamed_control_name


def test_template_backed_control_patch_updates_name_and_enabled_together(
    client: TestClient,
) -> None:
    # Given: a template-backed control
    control_id, _ = _create_template_control_with_name(client)
    renamed_control_name = f"patched-template-control-{uuid.uuid4()}"

    # When: patching both user-managed metadata fields together
    patch_response = client.patch(
        f"/api/v1/controls/{control_id}",
        json={"name": renamed_control_name, "enabled": False},
    )

    # Then: the metadata updates persist without losing template metadata
    assert patch_response.status_code == 200, patch_response.text
    body = patch_response.json()
    assert body["name"] == renamed_control_name
    assert body["enabled"] is False

    get_response = client.get(f"/api/v1/controls/{control_id}")
    assert get_response.status_code == 200, get_response.text
    get_body = get_response.json()
    assert get_body["name"] == renamed_control_name
    assert get_body["data"]["enabled"] is False
    assert get_body["data"]["template"]["description"] == "Regex denial template"
    assert get_body["data"]["template_values"] == {
        "pattern": "hello",
        "step_name": "templated-step",
    }


def test_template_backed_control_update_changes_scope_behavior(client: TestClient) -> None:
    # Given: an attached template-backed control
    control_id, control_name = _create_template_control_with_name(client)
    agent_name = _assign_control_to_agent(client, control_id)

    # When: updating the template values to change the rendered scope
    initial_eval = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    assert initial_eval.status_code == 200, initial_eval.text
    assert initial_eval.json()["is_safe"] is False

    updated_payload = _template_payload()
    updated_payload["template_values"] = {
        "pattern": "hello",
        "step_name": "updated-step",
    }
    update_response = client.put(
        f"/api/v1/controls/{control_id}/data",
        json={"data": updated_payload},
    )
    assert update_response.status_code == 200, update_response.text

    old_scope_eval = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    assert old_scope_eval.status_code == 200, old_scope_eval.text
    assert old_scope_eval.json()["is_safe"] is True

    updated_scope_eval = _evaluate_step(
        client,
        agent_name,
        step_name="updated-step",
        input_value="hello",
    )
    # Then: the old scope stops matching and the new scope starts matching
    assert updated_scope_eval.status_code == 200, updated_scope_eval.text
    body = updated_scope_eval.json()
    assert body["is_safe"] is False
    assert body["matches"][0]["control_name"] == control_name


def test_template_backed_control_supports_direct_agent_attachment(client: TestClient) -> None:
    # Given: a template-backed control attached directly to an agent
    control_id, control_name = _create_template_control_with_name(client)
    agent_name = _assign_control_to_agent(client, control_id, via_policy=False)

    # When: evaluating a matching step
    response = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )

    # Then: the directly attached control participates in evaluation
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_safe"] is False
    assert body["matches"][0]["control_name"] == control_name


def test_template_backed_observe_control_evaluates_as_safe_with_observe_match(
    client: TestClient,
) -> None:
    # Given: a template-backed control whose rendered action is observe
    payload = _template_payload()
    payload["template"] = deepcopy(payload["template"])
    payload["template"]["definition_template"]["action"]["decision"] = "observe"  # type: ignore[index]
    control_id, control_name = _create_template_control_with_name(
        client,
        payload,
        name_prefix="observe-template-control",
    )
    agent_name = _assign_control_to_agent(client, control_id)

    # When: evaluating a matching step
    response = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )

    # Then: the evaluation remains safe and returns the canonical observe action
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_safe"] is True
    assert len(body["matches"]) == 1
    assert body["matches"][0]["control_name"] == control_name
    assert body["matches"][0]["action"] == "observe"


def test_template_backed_control_preserves_falsey_values_and_uses_them_in_behavior(
    client: TestClient,
) -> None:
    # Given: a template-backed control created with falsey template values
    payload = _case_sensitive_template_payload(values=[], case_sensitive=False)
    control_id, control_name = _create_template_control_with_name(
        client,
        payload,
        name_prefix="falsey-template-control",
    )
    agent_name = _assign_control_to_agent(client, control_id)

    # When: inspecting stored data, evaluating, then updating to non-empty values
    get_response = client.get(f"/api/v1/controls/{control_id}/data")
    assert get_response.status_code == 200, get_response.text
    data = get_response.json()["data"]
    assert data["template_values"] == {
        "values": [],
        "case_sensitive": False,
    }

    non_applicable_eval = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    assert non_applicable_eval.status_code == 200, non_applicable_eval.text
    assert non_applicable_eval.json()["is_safe"] is True

    updated_payload = _case_sensitive_template_payload(
        values=["HELLO"],
        case_sensitive=False,
    )
    update_response = client.put(
        f"/api/v1/controls/{control_id}/data",
        json={"data": updated_payload},
    )
    assert update_response.status_code == 200, update_response.text

    deny_eval = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )
    # Then: falsey values persist and later updates change evaluation behavior
    assert deny_eval.status_code == 200, deny_eval.text
    body = deny_eval.json()
    assert body["is_safe"] is False
    assert body["matches"][0]["control_name"] == control_name


def test_mixed_raw_and_template_backed_controls_obey_deny_precedence(
    client: TestClient,
) -> None:
    # Given: an agent with both a template-backed deny control and a raw observe control
    template_control_id, template_control_name = _create_template_control_with_name(client)
    agent_name = _assign_control_to_agent(client, template_control_id)

    policy_response = client.get(f"/api/v1/agents/{agent_name}/policy")
    assert policy_response.status_code == 200, policy_response.text
    policy_id = policy_response.json()["policy_id"]

    raw_observe_name = f"raw-observe-{uuid.uuid4()}"
    raw_observe_response = client.put(
        "/api/v1/controls",
        json={
            "name": raw_observe_name,
            "data": _raw_control_payload("hello", action="observe"),
        },
    )
    assert raw_observe_response.status_code == 200, raw_observe_response.text
    raw_observe_control_id = raw_observe_response.json()["control_id"]

    add_control_response = client.post(
        f"/api/v1/policies/{policy_id}/controls/{raw_observe_control_id}"
    )
    assert add_control_response.status_code == 200, add_control_response.text

    # When: evaluating a step that matches both controls
    response = _evaluate_step(
        client,
        agent_name,
        step_name="templated-step",
        input_value="hello",
    )

    # Then: both matches are returned, advisory actions are canonicalized, and deny wins
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_safe"] is False
    assert len(body["matches"]) == 2
    names = {match["control_name"] for match in body["matches"]}
    actions = {match["action"] for match in body["matches"]}
    assert names == {template_control_name, raw_observe_name}
    assert actions == {"deny", "observe"}


def test_raw_control_can_be_replaced_with_template_backed_control(client: TestClient) -> None:
    # Given: an existing raw control
    control_id = _create_raw_control(client)

    # When: replacing its data with template-backed control input
    put_response = client.put(
        f"/api/v1/controls/{control_id}/data",
        json={"data": _template_payload()},
    )
    assert put_response.status_code == 200, put_response.text

    # Then: the stored control becomes template-backed and persists rendered values
    get_response = client.get(f"/api/v1/controls/{control_id}/data")
    assert get_response.status_code == 200, get_response.text
    data = get_response.json()["data"]
    assert data["template"]["description"] == "Regex denial template"
    assert data["template_values"]["pattern"] == "hello"
    assert data["condition"]["evaluator"]["config"]["pattern"] == "hello"


def test_raw_control_failed_template_replacement_does_not_mutate_raw_control(
    client: TestClient,
) -> None:
    # Given: an existing raw control and invalid template-backed replacement input
    control_id = _create_raw_control(client)
    original_response = client.get(f"/api/v1/controls/{control_id}/data")
    assert original_response.status_code == 200, original_response.text
    original_data = original_response.json()["data"]

    invalid_payload = _template_payload()
    invalid_payload["template_values"] = {"pattern": "["}

    # When: replacing the raw control with invalid template-backed input
