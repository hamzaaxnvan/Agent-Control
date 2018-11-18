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
