"""Tests for template-backed control model contracts."""

from __future__ import annotations

import pytest
from agent_control_models import (
    ControlDefinition,
    ControlDefinitionRuntime,
    TemplateControlInput,
    TemplateDefinition,
)
from agent_control_models.server import CreateControlRequest
from pydantic import ValidationError


VALID_TEMPLATE = {
    "parameters": {
        "pattern": {
            "type": "regex_re2",
            "label": "Pattern",
        }
    },
    "definition_template": {
        "description": "Template-backed control",
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
}


def _nested_template_value(depth: int) -> object:
    value: object = "leaf"
    for _ in range(depth):
        value = {"nested": value}
    return value


def test_control_definition_requires_template_fields_together() -> None:
    # Given: a rendered control that only includes template metadata without template values
    with pytest.raises(
        ValidationError,
        match="template and template_values must both be present or both absent",
    ):
        # When: validating the control definition model
        ControlDefinition.model_validate(
            {
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "regex",
                        "config": {"pattern": "ok"},
                    },
                },
                "action": {"decision": "deny"},
                "template": VALID_TEMPLATE,
            }
        )
    # Then: the model rejects the partial template-backed control shape


def test_control_definition_rejects_template_values_without_template() -> None:
    # Given: a rendered control that only includes template values without template metadata
    with pytest.raises(
        ValidationError,
        match="template and template_values must both be present or both absent",
    ):
        # When: validating the control definition model
        ControlDefinition.model_validate(
            {
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "regex",
                        "config": {"pattern": "ok"},
                    },
                },
                "action": {"decision": "deny"},
                "template_values": {"pattern": "hello"},
            }
        )
    # Then: the model rejects the partial template-backed control shape


def test_template_definition_rejects_invalid_parameter_name() -> None:
    # Given: a template definition with an invalid parameter name
    with pytest.raises(
        ValidationError,
        match=r"Parameter names must match \[a-zA-Z_\]\[a-zA-Z0-9_\]\*",
    ):
        # When: validating the template definition model
        TemplateDefinition.model_validate(
            {
                "parameters": {
                    "bad.name": {
                        "type": "string",
                        "label": "Bad Name",
                    }
                },
                "definition_template": {},
            }
        )
    # Then: the invalid parameter name is rejected


def test_template_definition_rejects_excessive_nesting() -> None:
    # Given: a template definition whose structure exceeds the nesting limit
    with pytest.raises(
        ValidationError,
        match="definition_template nesting depth exceeds maximum",
    ):
        # When: validating the template definition model
        TemplateDefinition.model_validate(
            {
                "parameters": {},
                "definition_template": _nested_template_value(12),
            }
        )
    # Then: the model rejects the deeply nested template


def test_template_definition_allows_flat_arrays_at_depth() -> None:
    # Given: a template at nesting depth 11 (just under the limit) that
    # contains a flat list of strings — arrays should not count as depth.
    deep = _nested_template_value(11)
    # Inject a list at the deepest dict level
    node = deep
    while isinstance(node, dict) and "nested" in node:
        if not isinstance(node["nested"], dict):
            break
        node = node["nested"]
