"""Tests for the telemetry trace context provider contract."""

from typing import Any

import pytest

from agent_control_telemetry.trace_context import (
    clear_trace_context_provider,
    get_trace_context_from_provider,
    set_trace_context_provider,
)


def teardown_function() -> None:
    clear_trace_context_provider()
