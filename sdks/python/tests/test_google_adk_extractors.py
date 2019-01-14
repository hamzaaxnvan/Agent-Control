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
