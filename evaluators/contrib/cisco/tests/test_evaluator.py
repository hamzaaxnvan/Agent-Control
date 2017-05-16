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

    cfg = CiscoAIDefenseConfig()
    ev = CiscoAIDefenseEvaluator(cfg)
    res = await ev.evaluate("ok content")
    assert res.matched is False
    assert res.metadata and res.metadata.get("severity") == "LOW"
    assert "raw" not in (res.metadata or {})


@pytest.mark.asyncio
async def test_on_error_deny_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(self: AIDefenseClient, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(AIDefenseClient, "chat_inspect", boom, raising=True)

    cfg = CiscoAIDefenseConfig(on_error="deny")
    ev = CiscoAIDefenseEvaluator(cfg)
    res = await ev.evaluate("anything")
    assert res.matched is True  # fail-closed
    assert res.metadata and res.metadata.get("fallback_action") == "deny"


def test_missing_api_key_raises_on_init(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_DEFENSE_API_KEY", raising=False)

    cfg = CiscoAIDefenseConfig()
    with pytest.raises(ValueError, match="Missing Cisco AI Defense API key"):
        CiscoAIDefenseEvaluator(cfg)


@pytest.mark.asyncio
async def test_missing_is_safe_uses_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(self: AIDefenseClient, **kwargs):
        return {"severity": "LOW"}

    monkeypatch.setattr(AIDefenseClient, "chat_inspect", fake, raising=True)

    cfg = CiscoAIDefenseConfig(on_error="allow")
    ev = CiscoAIDefenseEvaluator(cfg)
    res = await ev.evaluate("text")
    assert res.matched is False
    assert res.error == "Cisco AI Defense response missing 'is_safe'"
    assert res.metadata and res.metadata.get("fallback_action") == "allow"
    assert "raw" not in (res.metadata or {})


@pytest.mark.asyncio
async def test_include_raw_response_success_and_missing_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    # Success path includes raw when flag is True
    success_payload = {"is_safe": True, "severity": "LOW", "classifications": {"a": 1}}

    async def success(self: AIDefenseClient, **kwargs):
        return success_payload

    monkeypatch.setattr(AIDefenseClient, "chat_inspect", success, raising=True)

    cfg = CiscoAIDefenseConfig(include_raw_response=True)
    ev = CiscoAIDefenseEvaluator(cfg)
    res = await ev.evaluate("ok")
    assert res.matched is False
    assert res.metadata and res.metadata.get("classifications") == {"a": 1}
