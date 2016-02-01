"""Tests for the Galileo Decision Models evaluator and Runners client."""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from importlib import metadata as importlib_metadata
from importlib import reload
from importlib.metadata import PackageNotFoundError
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from agent_control_evaluator_galileo.decision_models import (
    DecisionModelsExecutionContext,
    DecisionModelsEvaluator,
    DecisionModelsEvaluatorConfig,
    DecisionModelsInvokeInputs,
    DecisionModelsInvokeRequest,
    DecisionModelsInvokeResponse,
    GalileoDecisionModelsClient,
)
from agent_control_evaluator_galileo.decision_models import (
    evaluator as decision_models_evaluator_module,
)
from agent_control_evaluator_galileo.decision_models.client import _normalize_invoke_url
from agent_control_evaluator_galileo.decision_models.evaluator import _contains
from agent_control_evaluator_galileo.luna.client import (
    GalileoExecutionContext,
    ScorerInvokeInputs,
    ScorerInvokeRequest,
)
from agent_control_models import Step
from pydantic import ValidationError

EXTENSIONS = {
    "namespace_key": "org-1",
    "caller_id": "user-7",
    "target_type": "log_stream",
    "target_id": "run-9",
    "metadata": {"project_id": "project-3"},
}


def _decode_jwt_segment(segment: str) -> dict[str, Any]:
    padded = segment + ("=" * (-len(segment) % 4))
    return json.loads(urlsafe_b64decode(padded.encode()).decode())


def _evaluator(monkeypatch: pytest.MonkeyPatch, **config: Any) -> DecisionModelsEvaluator:
    monkeypatch.setenv("GALILEO_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("GALILEO_LUNA_INVOKE_URL", "http://runners:8090")
    monkeypatch.setenv("GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME", "enabled")
    monkeypatch.setenv("GALILEO_FEATURE_FLAG_DECISION_MODELS_EVALUATOR", "enabled")
    evaluator = DecisionModelsEvaluator(
        DecisionModelsEvaluatorConfig(scorer_id="scorer-a", scorer_version_id="version-a", **config)
    )
    return evaluator


def test_decision_models_registration_and_required_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the scorer-invoke runtime is available and pinned scorer config is required
    from agent_control_evaluators import get_evaluator, register_evaluator

    monkeypatch.setenv("GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME", "enabled")
    monkeypatch.setenv("GALILEO_FEATURE_FLAG_DECISION_MODELS_EVALUATOR", "enabled")
    register_evaluator(DecisionModelsEvaluator)
    assert get_evaluator("galileo.decision_models") is DecisionModelsEvaluator
    with pytest.raises(ValidationError, match="scorer_id"):
        DecisionModelsEvaluatorConfig(scorer_version_id="version-a")  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="scorer_version_id"):
        DecisionModelsEvaluatorConfig(scorer_id="scorer-a")  # type: ignore[call-arg]


def test_decision_models_availability_requires_both_feature_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME", "enabled")
    monkeypatch.delenv("GALILEO_FEATURE_FLAG_DECISION_MODELS_EVALUATOR", raising=False)
    assert DecisionModelsEvaluator.is_available() is False

    monkeypatch.setenv("GALILEO_FEATURE_FLAG_DECISION_MODELS_EVALUATOR", "enabled")
    assert DecisionModelsEvaluator.is_available() is True

    monkeypatch.setenv("GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME", "disabled")
    assert DecisionModelsEvaluator.is_available() is False


def test_missing_distribution_metadata_uses_development_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_distribution(_: str) -> str:
        raise PackageNotFoundError

    from agent_control_evaluators import clear_evaluators, get_all_evaluators, register_evaluator

    registered_evaluators = get_all_evaluators()
    monkeypatch.setattr(importlib_metadata, "version", missing_distribution)
    try:
        clear_evaluators()
        reloaded_module = reload(decision_models_evaluator_module)
        assert reloaded_module.DecisionModelsEvaluator.metadata.version == "0.0.0.dev"
    finally:
        clear_evaluators()
        for evaluator_class in registered_evaluators.values():
            register_evaluator(evaluator_class)


@pytest.mark.parametrize(
    ("value", "threshold", "expected"),
    [
        ("unsafe answer", "unsafe", True),
        ({"label": "unsafe"}, "unsafe", True),
        ({"label": "safe"}, "unsafe", False),
        (42, "unsafe", False),
    ],
)
def test_contains_comparison_handles_supported_and_unsupported_values(
    value: Any, threshold: Any, expected: bool
) -> None:
    assert _contains(value, threshold) is expected


def test_config_rejects_non_numeric_or_missing_thresholds() -> None:
    with pytest.raises(ValidationError, match="requires a numeric threshold"):
        DecisionModelsEvaluatorConfig(
            scorer_id="scorer-a",
            scorer_version_id="version-a",
            operator="gt",
            threshold=True,
        )
    with pytest.raises(ValidationError, match="threshold is required"):
        DecisionModelsEvaluatorConfig(
            scorer_id="scorer-a",
            scorer_version_id="version-a",
            operator="eq",
            threshold=None,
        )


def test_config_allows_missing_threshold_for_any_operator() -> None:
    config = DecisionModelsEvaluatorConfig(
        scorer_id="scorer-a",
        scorer_version_id="version-a",
        operator="any",
        threshold=None,
    )

    assert config.threshold is None


@pytest.mark.asyncio
async def test_client_url_resolution_prefers_explicit_url_then_luna_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GALILEO_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("GALILEO_LUNA_INVOKE_URL", "http://luna:8090")

    explicit_client = GalileoDecisionModelsClient(invoke_url="http://explicit:8090")
    environment_client = GalileoDecisionModelsClient()

    expected_path = "/api/v1/scorers/invoke"
    assert explicit_client.invoke_url == f"http://explicit:8090{expected_path}"
    assert environment_client.invoke_url == f"http://luna:8090{expected_path}"
    await explicit_client.close()
    await environment_client.close()


def test_client_requires_luna_invoke_url_when_no_explicit_url_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GALILEO_API_SECRET_KEY", "test-secret")
    monkeypatch.delenv("GALILEO_LUNA_INVOKE_URL", raising=False)

    with pytest.raises(ValueError, match="GALILEO_LUNA_INVOKE_URL"):
        GalileoDecisionModelsClient()


def test_invoke_request_requires_execution_context_and_serializes_nested_record() -> None:
    context = DecisionModelsExecutionContext(
        organization_id="org-1", user_id="user-7", project_id="project-3", run_id="run-9"
    )
    record = {
        "type": "trace",
        "input": "",
        "output": "",
        "spans": [{"type": "llm", "input": [{"role": "user", "content": "q"}]}],
    }
    request = DecisionModelsInvokeRequest(
        scorer_id="scorer-a",
        scorer_version_id="version-a",
        execution_context=context,
        record=record,
        inputs=DecisionModelsInvokeInputs(),
        config={"request_timeout_seconds": 8.0},
    )

    payload = request.to_dict()
    assert payload["execution_context"] == {
        "organization_id": "org-1",
        "user_id": "user-7",
        "project_id": "project-3",
        "run_id": "run-9",
    }
    assert payload["record"] == record
    assert payload["scorer_version_id"] == "version-a"
    assert payload["inputs"] == {"query": "", "response": ""}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "threshold", "operator", "expected"),
    [
        (0.82, 0.5, "gte", True),
        ("unsafe", "unsafe", "eq", True),
        (3, 2, "gte", True),
        ("safe", "safe", "ne", False),
        (["unsafe"], "unsafe", "contains", True),
    ],
)
async def test_decision_models_applies_local_comparison(
    monkeypatch: pytest.MonkeyPatch,
    score: Any,
    threshold: Any,
    operator: str,
    expected: bool,
) -> None:
    evaluator = _evaluator(monkeypatch, threshold=threshold, operator=operator)
    evaluator._client.invoke = AsyncMock(
        return_value=DecisionModelsInvokeResponse(score=score, status="success")
    )
    result = await evaluator.evaluate_with_extensions(
        "",
        Step(
            type="trace",
            name="root",
            input="",
            children=[Step(type="llm", name="answer", input="")],
        ),
        EXTENSIONS,
    )
    assert result.matched is expected
    await evaluator.aclose()


@pytest.mark.asyncio
async def test_child_only_trace_keeps_nested_span_and_execution_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator(monkeypatch)
    invoke = AsyncMock(return_value=DecisionModelsInvokeResponse(score=0.82, status="success"))
    evaluator._client.invoke = invoke
    step = Step(
        type="trace",
        name="root",
        input="",
        output="",
        children=[
            Step(
                type="tool",
                name="search",
                input={"query": "question"},
                children=[Step(type="retriever", name="docs", input="question", output=["doc"])],
            ),
            Step(type="llm", name="answer", input="question", output="answer"),
        ],
    )

    result = await evaluator.evaluate_with_extensions("", step, EXTENSIONS)

    assert result.matched is True
    call = invoke.await_args.kwargs
    assert call["scorer_version_id"] == "version-a"
    assert call["execution_context"].user_id == "user-7"
    record = call["step"]
    assert record.children[0].children[0].type == "retriever"
    assert call["inputs"].query == ""
    await evaluator.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["llm", "tool", "retriever", "trace", "session"])
async def test_supported_record_types_are_built_from_step_children(
    monkeypatch: pytest.MonkeyPatch, record_type: str
) -> None:
    evaluator = _evaluator(monkeypatch)
    invoke = AsyncMock(return_value=DecisionModelsInvokeResponse(score="yes", status="success"))
    evaluator._client.invoke = invoke
    if record_type == "session":
        step = Step(
            type="session",
            name="session",
            input="",
            children=[
                Step(
                    type="trace",
                    name="trace",
                    input="",
                    children=[Step(type="llm", name="llm", input="")],
                )
            ],
        )
    elif record_type == "trace":
        step = Step(
            type="trace", name="trace", input="", children=[Step(type="llm", name="llm", input="")]
        )
    elif record_type in {"tool", "retriever"}:
        step = Step(
            type=record_type,
            name=record_type,
            input={"query": "question"} if record_type == "tool" else "question",
            children=[Step(type="llm", name="llm", input="")],
        )
    else:
        step = Step(type="llm", name="llm", input="")
    await evaluator.evaluate_with_extensions("input", step, EXTENSIONS)
    assert invoke.await_args.kwargs["step"].type == record_type
    await evaluator.aclose()


@pytest.mark.asyncio
async def test_runtime_disabled_and_missing_context_return_errors_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator(monkeypatch)
    monkeypatch.setenv("GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME", "disabled")
    invoke = AsyncMock()
    evaluator._client.invoke = invoke

    result = await evaluator.evaluate_with_extensions(
        "question", Step(type="llm", name="answer", input="question"), EXTENSIONS
    )

    assert result.matched is False
    assert "runtime is disabled" in (result.error or "")
    assert invoke.await_count == 0
    direct_result = await evaluator.evaluate("question")
    assert "runtime is disabled" in (direct_result.error or "")
    missing_context = await evaluator.evaluate_with_extensions(
        "question", Step(type="llm", name="answer", input=""), None
    )
    assert missing_context.matched is False
    assert "authenticated execution metadata" in (missing_context.error or "")
    monkeypatch.setenv("GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME", "enabled")
    step_only_context = await evaluator.evaluate_with_context(
        "question", Step(type="llm", name="answer", input="question")
    )
    assert "Step context alone is not sufficient" in (step_only_context.error or "")
    await evaluator.aclose()


@pytest.mark.asyncio
async def test_empty_project_id_is_omitted_from_execution_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator(monkeypatch)
    invoke = AsyncMock(return_value=DecisionModelsInvokeResponse(score=0.9, status="success"))
    evaluator._client.invoke = invoke
    extensions = {**EXTENSIONS, "metadata": {"project_id": ""}}

    result = await evaluator.evaluate_with_extensions(
        "question", Step(type="llm", name="answer", input="question"), extensions
    )

    assert result.error is None
    assert invoke.await_args.kwargs["execution_context"].project_id is None
    await evaluator.aclose()

