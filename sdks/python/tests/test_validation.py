"""Unit tests for SDK validation helpers."""

import pytest

from agent_control.validation import ensure_agent_name


def test_ensure_agent_name_normalizes_to_lowercase() -> None:
    assert ensure_agent_name("Agent-Name_123") == "agent-name_123"
