"""Unit tests for Google ADK extractor helpers."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


class MockPart:
    def __init__(
        self,
        text: str | None = None,
        function_call: object | None = None,
        function_response: object | None = None,
    ):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response


class MockContent:
    def __init__(self, role: str = "user", parts: list[object] | None = None):
        self.role = role
        self.parts = parts or []


class MockLlmResponse:
    def __init__(self, content: object):
        self.content = content


class MockStructuredValue:
    def __init__(self, payload: object):
        self.payload = payload

    def model_dump(self, mode: str = "json") -> object:
        assert mode == "json"
        return self.payload


def _install_google_modules() -> None:
    google_mod = ModuleType("google")
    adk_mod = ModuleType("google.adk")
    models_mod = ModuleType("google.adk.models")
    genai_mod = ModuleType("google.genai")
    types_mod = ModuleType("google.genai.types")

    models_mod.LlmResponse = MockLlmResponse
    types_mod.Content = MockContent
    types_mod.Part = MockPart
    genai_mod.types = types_mod

    sys.modules["google"] = google_mod
    sys.modules["google.adk"] = adk_mod
    sys.modules["google.adk.models"] = models_mod
    sys.modules["google.genai"] = genai_mod
    sys.modules["google.genai.types"] = types_mod


@pytest.fixture
def extractor_module():
    _install_google_modules()
    module_name = "agent_control.integrations.google_adk._extractors"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    yield module
    sys.modules.pop(module_name, None)


