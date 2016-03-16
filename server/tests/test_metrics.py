from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_control_server.config import settings
from agent_control_server.main import METRICS_PATH, add_prometheus_metrics


def test_metrics_endpoint_public(unauthenticated_client: TestClient) -> None:
    # Given: an unauthenticated client
    # When: requesting the metrics endpoint
    response = unauthenticated_client.get(METRICS_PATH)
    # Then: metrics are publicly accessible
    assert response.status_code == 200


def test_metrics_output_contains_default_prefix(unauthenticated_client: TestClient) -> None:
    # Given: default metrics are enabled with the configured prefix
