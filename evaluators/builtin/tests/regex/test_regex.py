"""Tests for the regex evaluator and its config validation."""

from __future__ import annotations

import pytest
from agent_control_evaluators.regex.config import RegexEvaluatorConfig
from agent_control_evaluators.regex.evaluator import RegexEvaluator


class TestRegexConfig:
    """Pattern validation rejects invalid RE2 syntax at config time."""

    def test_valid_pattern_accepted(self):
        config = RegexEvaluatorConfig(pattern=r"\d{3}-\d{2}-\d{4}")
        assert config.pattern == r"\d{3}-\d{2}-\d{4}"

    def test_empty_pattern_accepted(self):
        # Empty string is technically a valid RE2 pattern (matches everything).
        config = RegexEvaluatorConfig(pattern="")
        assert config.pattern == ""

    def test_invalid_pattern_rejected(self):
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            RegexEvaluatorConfig(pattern="[invalid(regex")

    def test_flags_default_to_none(self):
        config = RegexEvaluatorConfig(pattern=r"\d+")
        assert config.flags is None

    def test_flags_can_be_specified(self):
        config = RegexEvaluatorConfig(pattern="secret", flags=["IGNORECASE"])
        assert config.flags == ["IGNORECASE"]


class TestRegexEvaluator:
    """Pattern matching against arbitrary data."""

    @pytest.mark.asyncio
