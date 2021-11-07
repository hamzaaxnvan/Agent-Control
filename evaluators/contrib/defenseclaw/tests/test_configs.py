"""Contract tests for the DefenseClaw evaluator configurations."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_control_evaluator_defenseclaw import (
    DefenseClawOpaPolicyConfig,
    DefenseClawRulePackConfig,
)


def _rule_pack_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "rule_pack": {
            "version": 1,
            "category": "agent-control",
            "rules": [
                {
                    "id": "AC-CMD-RM-RF",
                    "pattern": "rm\\s+-rf",
                    "title": "Recursive deletion",
                    "severity": "HIGH",
                    "confidence": 0.99,
                    "tags": ["filesystem"],
                }
            ],
        },
    }


def test_rule_pack_example_round_trips_with_fixed_fields() -> None:
    # Given: the supplied rule-pack example
    config = _rule_pack_config()

    # When: validating and serializing it
    serialized = DefenseClawRulePackConfig.model_validate(config).model_dump()

    # Then: fixed fields and nested rules are preserved
    assert serialized == config


def test_rule_pack_defaults_are_serialized() -> None:
    # Given: a rule pack omitting fields with fixed v1 defaults
    config = _rule_pack_config()
    config.pop("schema_version")
    rule_pack = config["rule_pack"]
    assert isinstance(rule_pack, dict)
    rule_pack.pop("version")
