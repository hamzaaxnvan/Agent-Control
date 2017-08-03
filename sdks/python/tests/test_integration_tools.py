"""Tests for framework-neutral available-tool normalization."""

import pytest

from agent_control.integrations._tools import normalize_strands_tool_specs


@pytest.mark.parametrize(
    "specs",
    [
        {"search": {}},
        ["not-a-tool-spec"],
        [{"description": "missing name"}],
        [{"name": ""}],
    ],
)
def test_normalizer_rejects_incomplete_strands_registries(specs: object) -> None:
    # Given/When: the purported complete registry has an invalid shape
