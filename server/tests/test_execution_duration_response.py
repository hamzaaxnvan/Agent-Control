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
