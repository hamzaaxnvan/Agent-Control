"""Direct tests for recursive condition-tree models."""

from __future__ import annotations

import pytest
from agent_control_models import (
    ControlDefinition,
    ControlDefinitionRuntime,
)
from agent_control_models.controls import ControlDefinitionBase
from pydantic import ValidationError


def _leaf(
    path: str,
    evaluator_name: str = "regex",
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "selector": {"path": path},
        "evaluator": {
            "name": evaluator_name,
            "config": config or {"pattern": "ok"},
        },
    }


def test_condition_leaf_requires_selector_and_evaluator() -> None:
    # Given: a leaf condition with only a selector
    with pytest.raises(
        ValidationError,
        match="Leaf condition requires both selector and evaluator",
    ):
        # When: validating the control definition
        ControlDefinition.model_validate(
            {
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {"selector": {"path": "input"}},
                "action": {"decision": "deny"},
            }
        )
    # Then: validation rejects the incomplete leaf shape


def test_condition_node_requires_exactly_one_shape() -> None:
    # Given: a condition node that mixes leaf and composite fields
    with pytest.raises(
        ValidationError,
        match="Condition node must contain exactly one of leaf, and, or, not",
    ):
        # When: validating the control definition
        ControlDefinition.model_validate(
            {
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {"name": "regex", "config": {"pattern": "ok"}},
                    "and": [_leaf("output")],
                },
                "action": {"decision": "deny"},
            }
        )
    # Then: validation rejects the ambiguous node shape


def test_legacy_leaf_payload_is_canonicalized() -> None:
    # Given: a legacy flat selector/evaluator payload
    legacy_payload = {
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["pre"]},
        "selector": {"path": "input"},
        "evaluator": {"name": "regex", "config": {"pattern": "ok"}},
        "action": {"decision": "deny"},
    }

    # When: validating the legacy payload
    control = ControlDefinition.model_validate(legacy_payload)

    # Then: the model dumps back out in canonical condition form
    dumped = control.model_dump(mode="json", exclude_none=True)
    assert "selector" not in dumped
    assert "evaluator" not in dumped
    assert dumped["condition"]["selector"]["path"] == "input"
    assert dumped["condition"]["evaluator"]["name"] == "regex"


def test_runtime_legacy_leaf_payload_is_canonicalized() -> None:
    # Given: a legacy flat selector/evaluator payload loaded for runtime evaluation
    legacy_payload = {
        "execution": "server",
