"""Tests for optional structured runtime context on Step."""

from agent_control_models import Step
from pydantic import ValidationError


def test_step_accepts_and_serializes_structured_tools_and_ground_truth() -> None:
    # Given: a runtime LLM step with structured scorer context
    payload = {
        "type": "llm",
        "name": "answer",
        "input": {"question": "Capital of France?"},
