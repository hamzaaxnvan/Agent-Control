"""Targeted tests covering match_mode branches and edge-case messages."""

from __future__ import annotations

import pytest
from agent_control_evaluators.list.config import ListEvaluatorConfig
from agent_control_evaluators.list.evaluator import ListEvaluator


@pytest.mark.asyncio
async def test_match_mode_contains_uses_word_boundary():
    """contains mode matches whole words but rejects sub-word matches."""
