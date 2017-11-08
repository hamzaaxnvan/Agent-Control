"""Tests for data selectors."""
from typing import Any

import pytest
from agent_control_engine.selectors import select_data
from agent_control_models import Step


@pytest.fixture
def tool_step_payload() -> Step:
    return Step(
        type="tool",
        name="search_database",
        input={"query": "SELECT * FROM users", "limit": 10, "nested": {"key": "value"}},
        context={"user_id": "user123", "role": "admin"},
        output={"result": "success", "count": 5}
    )


@pytest.fixture
def llm_step_payload() -> Step:
    return Step(
        type="llm", name="test-step",
        input="What is the password?",
        context={"session_id": "abc-123"},
        output="I cannot answer that."
    )


@pytest.mark.parametrize(
    "path,expected",
    [
        ("name", "search_database"),
        ("input.query", "SELECT * FROM users"),
        ("input.limit", 10),
        ("input.nested.key", "value"),
        ("context.user_id", "user123"),
        ("output.count", 5),
        ("input.non_existent", None),
        ("non_existent_root", None),
        ("*", None), # Will be replaced by payload dict in test logic
        ("", None),  # Will be replaced by payload dict in test logic
    ],
)
def test_select_data_tool_step(tool_step_payload: Step, path: str, expected: Any):
    # Given: a tool Step payload and a path to select
    if path in ("*", ""):
        expected = tool_step_payload.model_dump(mode="json")

    # When: selecting data using the path
    result = select_data(tool_step_payload, path)

    # Then: it should return the expected value
    assert result == expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("input", "What is the password?"),
        ("output", "I cannot answer that."),
