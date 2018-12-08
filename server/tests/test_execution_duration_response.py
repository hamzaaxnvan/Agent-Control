"""HTTP contract tests for per-control execution durations without database I/O."""

from unittest.mock import AsyncMock

import pytest
from agent_control_models import ControlMatch, EvaluationResponse, EvaluatorResult
from fastapi.testclient import TestClient

from agent_control_server.endpoints import evaluation
from agent_control_server.endpoints.evaluation import SAFE_EVALUATOR_ERROR


@pytest.fixture(scope="session", autouse=True)
def db_schema() -> None:
    """Override database setup: control loading is mocked for this contract test."""


@pytest.fixture(autouse=True)
def clean_db() -> None:
    """Override database cleanup: these tests neither read nor write database rows."""


@pytest.fixture
def engine_response(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub evaluation I/O while retaining the real HTTP response handling."""
    monkeypatch.setattr(evaluation, "_load_engine_controls", AsyncMock(return_value=[]))
    process = AsyncMock()
    monkeypatch.setattr(evaluation.ControlEngine, "process", process)
    return process


def test_evaluation_response_preserves_duration_for_each_result_category(
    client: TestClient,
    engine_response: AsyncMock,
) -> None:
    # Given: engine results with distinct per-control timings, including zero.
    # Control loading and engine processing are stubbed to avoid database/evaluator I/O.
    engine_response.return_value = EvaluationResponse(
        is_safe=False,
        confidence=0.9,
        matches=[
            ControlMatch(
                control_id=1,
                control_name="matched-control",
                action="deny",
                execution_duration_ms=12.5,
                result=EvaluatorResult(matched=True, confidence=0.9),
            )
        ],
        errors=[
            ControlMatch(
                control_id=2,
