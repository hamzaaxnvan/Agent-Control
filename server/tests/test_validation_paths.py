"""Tests for nested validation field path formatting."""

from agent_control_server.services.validation_paths import format_field_path


def test_format_field_path_renders_dot_and_bracket_notation() -> None:
    # Given: nested string and integer path parts
    # When: formatting the field path
    assert (
        format_field_path(
            ("data", "condition", "and", 0, "evaluator", "config", "logic")
