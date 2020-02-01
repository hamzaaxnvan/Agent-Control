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
