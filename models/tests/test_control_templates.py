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
