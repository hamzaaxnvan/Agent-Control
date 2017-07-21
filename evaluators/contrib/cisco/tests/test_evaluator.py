from importlib.metadata import PackageNotFoundError, version

import pytest
import agent_control_evaluator_cisco.ai_defense.evaluator as cisco_evaluator_module
from pydantic import ValidationError

from agent_control_evaluator_cisco.ai_defense import (
    CiscoAIDefenseEvaluator,
    CiscoAIDefenseConfig,
)
from agent_control_evaluator_cisco.ai_defense.client import AIDefenseClient


@pytest.fixture(autouse=True)
def _env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DEFENSE_API_KEY", "test-key")


def test_metadata_version_matches_distribution_version() -> None:
    assert CiscoAIDefenseEvaluator.metadata.version == version("agent-control-evaluator-cisco")


def test_metadata_version_falls_back_without_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_not_found(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(cisco_evaluator_module, "version", _raise_not_found)

    assert cisco_evaluator_module._resolve_package_version() == "0.0.0.dev"


@pytest.mark.asyncio
async def test_none_input_returns_no_data() -> None:
    cfg = CiscoAIDefenseConfig()
    ev = CiscoAIDefenseEvaluator(cfg)
    res = await ev.evaluate(None)
    assert res.matched is False
    assert res.error is None


@pytest.mark.asyncio
async def test_is_safe_false_triggers_match(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_chat_inspect(self: AIDefenseClient, **kwargs):
        return {"is_safe": False, "severity": "HIGH"}

    monkeypatch.setattr(AIDefenseClient, "chat_inspect", fake_chat_inspect, raising=True)

    cfg = CiscoAIDefenseConfig()
    ev = CiscoAIDefenseEvaluator(cfg)
    res = await ev.evaluate("bad content")
    assert res.matched is True
    assert res.metadata and res.metadata.get("severity") == "HIGH"


@pytest.mark.asyncio
async def test_is_safe_true_is_not_matched(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_chat_inspect(self: AIDefenseClient, **kwargs):
        return {"is_safe": True, "severity": "LOW"}

    monkeypatch.setattr(AIDefenseClient, "chat_inspect", fake_chat_inspect, raising=True)
