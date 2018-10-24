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
