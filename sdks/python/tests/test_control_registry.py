"""Tests for control step registry behavior."""

from __future__ import annotations

import functools
import logging
from collections.abc import Generator
from typing import Any

import pytest
from agent_control._control_registry import (
    clear,
    get_registered_steps,
    merge_explicit_and_auto_steps,
    register,
)
from pydantic import BaseModel


@pytest.fixture(autouse=True)
def _clean_registry() -> Generator[None, None, None]:
    """Ensure each test starts with an empty registry."""
    clear()
    yield
    clear()


class TestRegister:
    """Tests for register() and get_registered_steps()."""

    def test_register_simple_function(self) -> None:
        # Given a basic typed control function with a docstring.
        def chat(message: str) -> str:
            """Chat with the agent."""
            ...

        # When the function is registered and steps are retrieved.
        register(chat)
        steps = get_registered_steps()

        # Then one llm step is created with the expected name, description, and schemas.
        assert len(steps) == 1
        step = steps[0]
        assert step["name"] == "chat"
        assert step["type"] == "llm"
        assert step["description"] == "Chat with the agent."
        assert step["input_schema"]["type"] == "object"
        assert step["output_schema"]["type"] == "string"

    def test_register_tool_function(self) -> None:
        """Functions with .name or .tool_name should be registered as tools."""

        # Given a function that advertises tool-style metadata via attributes.
        def search_db(query: str, limit: int = 10) -> str:
            """Search the database."""
            ...

        search_db.name = "search_db"  # type: ignore[attr-defined]
        search_db.tool_name = "search_db"  # type: ignore[attr-defined]

        # When the function is registered.
        register(search_db)
        steps = get_registered_steps()

        # Then the registered step is classified as a tool using the declared tool name.
        assert len(steps) == 1
        assert steps[0]["type"] == "tool"
        assert steps[0]["name"] == "search_db"

    def test_register_explicit_custom_type(self) -> None:
        """An explicit type overrides the default LLM inference."""

        def retrieve(query: str) -> str:
            ...

        register(retrieve, step_type=" retriever ")

        assert get_registered_steps()[0]["type"] == "retriever"

    def test_register_with_policy(self) -> None:
        # Given a typed function and an explicit policy value at registration time.
        def my_func(x: str) -> str:
            ...

        # When the function is registered with that policy.
        register(my_func, policy="safety-policy")
        steps = get_registered_steps()

        # Then metadata contains the policy exactly once.
        assert steps[0]["metadata"] == {"policy": "safety-policy"}

    def test_register_no_policy_no_metadata(self) -> None:
        # Given a typed function registered without policy metadata.
        def my_func(x: str) -> str:
            ...

        # When registration completes.
        register(my_func)
        steps = get_registered_steps()

        # Then no metadata field is emitted for the step.
        assert "metadata" not in steps[0]

    def test_deduplicate_by_name(self) -> None:
        """Registering two functions with the same name should keep the last one."""

        # Given two functions that resolve to the same step name.
        def chat(message: str) -> str:
            """First version."""
            ...

        def chat_v2(message: str) -> int:  # noqa: ARG001
            """Second version."""
            ...

        chat_v2.__name__ = "chat"  # simulate same name

        # When both are registered in order.
        register(chat)
        register(chat_v2)
        steps = get_registered_steps()

        # Then only the second registration remains for that name.
        assert len(steps) == 1
        assert steps[0]["description"] == "Second version."

    def test_same_name_different_types_are_kept_distinct(self) -> None:
        # Given two controls that share a name but represent different step types.
        def llm_step(message: str) -> str:
            """LLM variant."""
            ...

        def tool_step(query: str) -> str:
            """Tool variant."""
            ...

        llm_step.__name__ = "shared_name"
        tool_step.name = "shared_name"  # type: ignore[attr-defined]
        tool_step.tool_name = "shared_name"  # type: ignore[attr-defined]

        # When both controls are registered.
        register(llm_step)
        register(tool_step)
        steps = get_registered_steps()

        # Then both entries are retained because deduplication key is (type, name).
        keys = {(step["type"], step["name"]) for step in steps}
        assert keys == {("llm", "shared_name"), ("tool", "shared_name")}

    def test_no_docstring(self) -> None:
        # Given a typed function without a docstring.
        def my_func(x: str) -> str:
            ...

        # When the function is registered.
        register(my_func)
        steps = get_registered_steps()

        # Then description is omitted from the resulting step.
        assert "description" not in steps[0]

    def test_no_type_hints(self) -> None:
        """Untyped functions still register with permissive schemas."""

        # Given an untyped function.
        def my_func(x, y):
            ...

        # When the function is registered.
        register(my_func)
        steps = get_registered_steps()

        # Then registration succeeds with a permissive input schema and fallback output schema.
        assert len(steps) == 1
        assert steps[0]["name"] == "my_func"
        assert steps[0]["input_schema"]["type"] == "object"
        assert set(steps[0]["input_schema"]["properties"]) == {"x", "y"}
        assert steps[0]["output_schema"] == {}

    def test_forward_reference_can_resolve_at_retrieval_time(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Given a function registered before its forward-referenced model is available in globals.
        def my_func(payload: LaterModel) -> str:
            ...

        register(my_func)

