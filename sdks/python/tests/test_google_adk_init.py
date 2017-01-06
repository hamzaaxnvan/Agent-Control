"""Unit tests for Google ADK lazy imports."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def test_google_adk_init_all():
    import agent_control.integrations.google_adk as google_adk_module

    assert google_adk_module.__all__ == ["AgentControlPlugin"]


def test_google_adk_lazy_import_fails_without_dependency():
    import agent_control.integrations.google_adk as google_adk_module

    removed: dict[str, ModuleType] = {}
    for module_name in list(sys.modules):
        if module_name == "google" or module_name.startswith("google."):
            module = sys.modules.pop(module_name)
            if isinstance(module, ModuleType):
                removed[module_name] = module
    sys.modules.pop("agent_control.integrations.google_adk.plugin", None)

    try:
        with pytest.raises(RuntimeError, match="google-adk"):
            _ = google_adk_module.AgentControlPlugin
    finally:
        sys.modules.update(removed)


def test_google_adk_lazy_import_succeeds_with_mocked_modules():
