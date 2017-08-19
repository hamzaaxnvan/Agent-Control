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
    rule_pack.pop("category")

    # When: validating and serializing it
    serialized = DefenseClawRulePackConfig.model_validate(config).model_dump()

    # Then: the wire-contract constants are materialized
    assert serialized["schema_version"] == 1
    assert serialized["rule_pack"]["version"] == 1
    assert serialized["rule_pack"]["category"] == "agent-control"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), 2),
        (("rule_pack", "version"), 2),
        (("rule_pack", "category"), "other"),
        (("rule_pack", "rules", 0, "severity"), "URGENT"),
        (("rule_pack", "rules", 0, "confidence"), -0.1),
        (("rule_pack", "rules", 0, "confidence"), 1.1),
    ],
)
def test_rule_pack_rejects_unsupported_values(path: tuple[object, ...], value: object) -> None:
    # Given: a valid config with one unsupported nested value
    config = _rule_pack_config()
    target: object = config
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    # When/Then: typed validation rejects it
    with pytest.raises(ValidationError):
        DefenseClawRulePackConfig.model_validate(config)


def test_rule_pack_rejects_empty_and_duplicate_rules() -> None:
    # Given: an empty rule list
    empty = _rule_pack_config()
    empty["rule_pack"]["rules"] = []  # type: ignore[index]

    # When/Then: at least one rule is required
    with pytest.raises(ValidationError):
        DefenseClawRulePackConfig.model_validate(empty)

    # Given: duplicate rule IDs
    duplicate = _rule_pack_config()
    first_rule = duplicate["rule_pack"]["rules"][0]  # type: ignore[index]
    duplicate["rule_pack"]["rules"].append(dict(first_rule))  # type: ignore[index,union-attr]

    # When/Then: duplicate IDs are rejected
    with pytest.raises(ValidationError, match="rule ids must be unique"):
        DefenseClawRulePackConfig.model_validate(duplicate)
