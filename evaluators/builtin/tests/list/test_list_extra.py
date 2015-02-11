"""Targeted tests covering match_mode branches and edge-case messages."""

from __future__ import annotations

import pytest
from agent_control_evaluators.list.config import ListEvaluatorConfig
from agent_control_evaluators.list.evaluator import ListEvaluator


@pytest.mark.asyncio
async def test_match_mode_contains_uses_word_boundary():
    """contains mode matches whole words but rejects sub-word matches."""
    config = ListEvaluatorConfig(values=["admin"], match_mode="contains")
    evaluator = ListEvaluator(config)

    matched = await evaluator.evaluate("the admin user logged in")
    assert matched.matched is True

    not_matched = await evaluator.evaluate("administrator")  # sub-word, no boundary
    assert not_matched.matched is False


@pytest.mark.asyncio
async def test_match_mode_exact_is_the_default():
    """No explicit mode uses anchored exact matching."""
