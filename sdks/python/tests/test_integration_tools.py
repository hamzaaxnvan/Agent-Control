"""Tests for framework-neutral available-tool normalization."""

import pytest

from agent_control.integrations._tools import normalize_strands_tool_specs


@pytest.mark.parametrize(
    "specs",
