"""Tests for unified evaluator factory."""

import pytest
from agent_control_engine import (
    clear_evaluator_cache,
    get_evaluator_instance,
    list_evaluators,
)
from agent_control_models import EvaluatorSpec
from agent_control_evaluators import (
    ListEvaluator,
    RegexEvaluator,
    RegexEvaluatorConfig,
)


class TestRegexEvaluator:
    """Tests for the regex evaluator via the evaluator factory."""

    @pytest.mark.asyncio
    async def test_basic_match(self):
        """Test regex matches SSN pattern."""
        # Given: A regex evaluator with SSN pattern
        config = EvaluatorSpec(name="regex", config={"pattern": r"\d{3}-\d{2}-\d{4}"})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating text containing SSN
        result = await evaluator.evaluate("My SSN is 123-45-6789")

        # Then: Should match with high confidence
        assert result.matched is True
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_no_match(self):
        """Test regex doesn't match when pattern not found."""
        # Given: A regex evaluator with SSN pattern
        config = EvaluatorSpec(name="regex", config={"pattern": r"\d{3}-\d{2}-\d{4}"})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating text without pattern
        result = await evaluator.evaluate("No numbers here")

        # Then: Should not match
        assert result.matched is False
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_non_string_input(self):
        """Test non-string input is converted to string."""
        # Given: A regex evaluator
        config = EvaluatorSpec(name="regex", config={"pattern": r"123"})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating non-string input
        result = await evaluator.evaluate(12345)

        # Then: Should match after conversion
        assert result.matched is True

    @pytest.mark.asyncio
    async def test_none_input(self):
        """Test handling of None input."""
        # Given: A regex evaluator
        config = EvaluatorSpec(name="regex", config={"pattern": r".*"})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating None
        result = await evaluator.evaluate(None)

        # Then: Should not match and return message
        assert result.matched is False
        assert result.message == "No data to match"

    def test_invalid_regex_pattern(self):
        """Test invalid regex pattern raises error."""
        # Given/When: Creating config with invalid pattern
        # Then: Should raise ValueError
        with pytest.raises(ValueError):
            RegexEvaluatorConfig(pattern="[")

    @pytest.mark.asyncio
    async def test_empty_pattern_matches_everything(self):
        """Test empty pattern matches everything."""
        # Given: A regex evaluator with empty pattern
        config = EvaluatorSpec(name="regex", config={"pattern": ""})
        evaluator = get_evaluator_instance(config)

        # When: Evaluating any text
        result = await evaluator.evaluate("something")

        # Then: Should match
        assert result.matched is True


class TestListEvaluator:
    """Tests for the list evaluator via the evaluator factory."""

    @pytest.mark.asyncio
    async def test_any_match(self):
        """Test list evaluator with any/match logic."""
        # Given: A list evaluator with blocklist items
        config = EvaluatorSpec(
            name="list",
            config={"values": ["bad", "evil"], "logic": "any", "match_on": "match"},
        )
        evaluator = get_evaluator_instance(config)

        # When/Then: Blocklist items match, others don't
        assert (await evaluator.evaluate("bad")).matched is True
        assert (await evaluator.evaluate("evil")).matched is True
        assert (await evaluator.evaluate("good")).matched is False

    @pytest.mark.asyncio
    async def test_any_no_match(self):
        """Test list evaluator as allowlist (any/no_match)."""
        # Given: A list evaluator as allowlist
        config = EvaluatorSpec(
            name="list",
            config={"values": ["safe", "ok"], "logic": "any", "match_on": "no_match"},
        )
        evaluator = get_evaluator_instance(config)

        # When/Then: Allowlist items don't match, others do
        assert (await evaluator.evaluate("safe")).matched is False
        assert (await evaluator.evaluate("ok")).matched is False
        assert (await evaluator.evaluate("dangerous")).matched is True

    @pytest.mark.asyncio
    async def test_all_match(self):
        """Test list evaluator with all/match logic."""
        # Given: A list evaluator with all/match logic
        config = EvaluatorSpec(
            name="list",
            config={"values": ["valid1", "valid2"], "logic": "all", "match_on": "match"},
        )
        evaluator = get_evaluator_instance(config)

        # When/Then: Matches only when all values present
        assert (await evaluator.evaluate(["valid1", "valid2"])).matched is True
        assert (await evaluator.evaluate(["valid1", "invalid"])).matched is False
        assert (await evaluator.evaluate([])).matched is False

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        """Test case-insensitive matching."""
        # Given: A case-insensitive list evaluator
        config = EvaluatorSpec(
            name="list",
            config={"values": ["MixedCase"], "case_sensitive": False, "match_on": "match"},
        )
        evaluator = get_evaluator_instance(config)

        # When/Then: Matches regardless of case
        assert (await evaluator.evaluate("mixedcase")).matched is True
        assert (await evaluator.evaluate("MIXEDCASE")).matched is True


class TestGetEvaluatorInstance:
    """Tests for the get_evaluator_instance factory function."""

    def test_get_evaluator_instance_returns_correct_type(self):
        """Test factory returns correct evaluator type."""
        # Given: An evaluator config
        config = EvaluatorSpec(name="regex", config={"pattern": "abc"})
        # When: Getting evaluator
        evaluator = get_evaluator_instance(config)

        # Then: Returns correct evaluator type
        assert isinstance(evaluator, RegexEvaluator)
        assert evaluator.config.pattern == "abc"

    def test_get_evaluator_instance_unknown_evaluator(self):
        """Test error when evaluator not found."""
        # Given: Config for nonexistent evaluator
        config = EvaluatorSpec(name="nonexistent", config={})

        # When/Then: Should raise ValueError
        with pytest.raises(ValueError, match="not found"):
            get_evaluator_instance(config)

    def test_list_evaluators(self):
        """Test listing available evaluators."""
        # Given/When: Getting available evaluators
