from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_control_server.config import settings
from agent_control_server.main import METRICS_PATH, add_prometheus_metrics


def test_metrics_endpoint_public(unauthenticated_client: TestClient) -> None:
