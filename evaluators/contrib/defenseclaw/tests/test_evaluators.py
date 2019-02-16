"""Behavior tests for the DefenseClaw no-op evaluators."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from agent_control_evaluator_defenseclaw import (
    DefenseClawOpaPolicyEvaluator,
    DefenseClawRulePackEvaluator,
)


def _rule_pack_config() -> dict[str, object]:
    return {
        "rule_pack": {
            "rules": [
                {
                    "id": "rule-1",
                    "pattern": "example",
                    "title": "Example",
                    "severity": "LOW",
                    "confidence": 1.0,
                    "tags": [],
                }
            ]
        }
    }


def test_metadata_names_are_distinct_public_identifiers() -> None:
    assert DefenseClawRulePackEvaluator.metadata.name == "defenseclaw.rule_pack"
    assert DefenseClawOpaPolicyEvaluator.metadata.name == "defenseclaw.opa_policy"
    assert DefenseClawRulePackEvaluator is not DefenseClawOpaPolicyEvaluator


def test_entry_points_match_public_metadata_names() -> None:
    # Given: the installed-package manifest contract
    manifest_path = Path(__file__).parent.parent / "pyproject.toml"
    manifest = tomllib.loads(manifest_path.read_text())
