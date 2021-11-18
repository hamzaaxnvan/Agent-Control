"""Unit tests for Google ADK plugin integration."""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_control import ControlSteerError, ControlViolationError
from agent_control._state import state


class MockBasePlugin:
    def __init__(self, name: str | None = None):
        self.base_name = name


class MockPart:
    def __init__(self, text: str | None = None):
        self.text = text


class MockContent:
    def __init__(self, role: str = "user", parts: list[object] | None = None):
        self.role = role
        self.parts = parts or []


class MockConfig:
    def __init__(self, system_instruction: str | None = None):
        self.system_instruction = system_instruction


class MockLlmRequest:
    def __init__(
        self,
        text: str = "hello",
        config: object | None = None,
        request_id: str | None = None,
        tools_dict: dict[str, object] | None = None,
    ):
        self.contents = [SimpleNamespace(parts=[MockPart(text)])]
        self.config = config if config is not None else MockConfig()
        self.request_id = request_id
        if tools_dict is not None:
            self.tools_dict = tools_dict


class MockLlmResponse:
    def __init__(self, content: object, request_id: str | None = None):
        self.content = content
        self.request_id = request_id


class MockTool:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def run(self, city: str) -> dict[str, str]:
        return {"city": city}


class MockToolContext:
    def __init__(
        self,
        agent_name: str | None = None,
        callback_context: object | None = None,
    ):
        self.agent_name = agent_name
        self.callback_context = callback_context


class MockCallbackContext:
    def __init__(self, agent_name: str, invocation_id: str | None = None):
        self.agent_name = agent_name
        self.invocation_id = invocation_id
        self.agent = SimpleNamespace(name=agent_name, description=f"{agent_name} desc")


def _install_google_modules() -> None:
    google_mod = ModuleType("google")
    adk_mod = ModuleType("google.adk")
    callback_context_mod = ModuleType("google.adk.agents.callback_context")
    models_mod = ModuleType("google.adk.models")
    plugins_mod = ModuleType("google.adk.plugins")
    tools_mod = ModuleType("google.adk.tools")
    tool_context_mod = ModuleType("google.adk.tools.tool_context")
    genai_mod = ModuleType("google.genai")
    types_mod = ModuleType("google.genai.types")

    callback_context_mod.CallbackContext = MockCallbackContext
    models_mod.LlmRequest = MockLlmRequest
    models_mod.LlmResponse = MockLlmResponse
    plugins_mod.BasePlugin = MockBasePlugin
    tools_mod.BaseTool = MockTool
    tool_context_mod.ToolContext = MockToolContext
    types_mod.Content = MockContent
    types_mod.Part = MockPart
    genai_mod.types = types_mod

    sys.modules["google"] = google_mod
    sys.modules["google.adk"] = adk_mod
    sys.modules["google.adk.agents.callback_context"] = callback_context_mod
    sys.modules["google.adk.models"] = models_mod
    sys.modules["google.adk.plugins"] = plugins_mod
    sys.modules["google.adk.tools"] = tools_mod
    sys.modules["google.adk.tools.tool_context"] = tool_context_mod
    sys.modules["google.genai"] = genai_mod
    sys.modules["google.genai.types"] = types_mod


@pytest.fixture
def plugin_module():
    _install_google_modules()
    for name in (
        "agent_control.integrations.google_adk._extractors",
        "agent_control.integrations.google_adk.plugin",
    ):
        sys.modules.pop(name, None)
    module = importlib.import_module("agent_control.integrations.google_adk.plugin")
    yield module
    for name in (
        "agent_control.integrations.google_adk._extractors",
        "agent_control.integrations.google_adk.plugin",
    ):
        sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def reset_state():
    original_agent = state.current_agent
    original_server_url = state.server_url
    original_api_key = state.api_key
    original_controls = state.server_controls
    state.current_agent = None
    state.server_url = None
    state.api_key = None
    state.server_controls = None
    yield
    state.current_agent = original_agent
    state.server_url = original_server_url
    state.api_key = original_api_key
    state.server_controls = original_controls


def test_init_rejects_mismatched_current_agent(plugin_module):
    state.current_agent = SimpleNamespace(agent_name="different-agent")

    with pytest.raises(ValueError, match="must match"):
        plugin_module.AgentControlPlugin(agent_name="test-agent01")


@pytest.mark.asyncio
async def test_before_model_safe(plugin_module):
    plugin = plugin_module.AgentControlPlugin(agent_name="test-agent01")
    context = MockCallbackContext("researcher")
    request = MockLlmRequest("hello")

    with patch.object(
        plugin_module,
        "_evaluate_and_enforce",
        AsyncMock(return_value=MagicMock()),
    ) as mock_eval, patch.object(plugin, "_schedule_step_sync") as mock_schedule:
        result = await plugin.before_model_callback(
