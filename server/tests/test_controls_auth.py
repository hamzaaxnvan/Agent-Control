"""HTTP-level auth coverage for ``/controls`` and ``/control-templates``."""

from __future__ import annotations

import uuid

from agent_control_server.auth_framework import set_authorizer
from agent_control_server.auth_framework.providers import NoAuthProvider
from fastapi.testclient import TestClient

from .utils import VALID_CONTROL_PAYLOAD

_CONTROLS_URL = "/api/v1/controls"
_TEMPLATES_URL = "/api/v1/control-templates"


def _valid_template_render_payload() -> dict[str, object]:
    return {
        "template": {
            "description": "Regex denial template",
            "parameters": {
                "pattern": {
                    "type": "regex_re2",
                    "label": "Pattern",
                },
            },
            "definition_template": {
                "description": "Template-backed control",
                "execution": "server",
                "scope": {"step_types": ["llm"], "stages": ["pre"]},
                "condition": {
                    "selector": {"path": "input"},
                    "evaluator": {
                        "name": "regex",
                        "config": {"pattern": {"$param": "pattern"}},
                    },
                },
                "action": {"decision": "deny"},
            },
        },
        "template_values": {"pattern": "hello"},
    }


def _create_control(client: TestClient, name: str | None = None) -> int:
    payload = {
        "name": name or f"control-{uuid.uuid4().hex[:12]}",
        "data": VALID_CONTROL_PAYLOAD,
    }
    resp = client.put(_CONTROLS_URL, json=payload)
    assert resp.status_code == 200, resp.text
    return int(resp.json()["control_id"])


# ---------------------------------------------------------------------------
# /controls/schema is intentionally public metadata.
# ---------------------------------------------------------------------------


def test_schema_endpoint_reachable_without_credentials(
    unauthenticated_client: TestClient,
) -> None:
    # Given: a client that never sends an API key
    # When: the schema endpoint is fetched
    resp = unauthenticated_client.get(f"{_CONTROLS_URL}/schema")

    # Then: the canonical ControlDefinition schema is returned
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "schema" in body
    assert isinstance(body["schema"], dict)


def test_schema_endpoint_reachable_with_admin_key(client: TestClient) -> None:
    # Given: an admin client
    # When: the schema endpoint is fetched
    resp = client.get(f"{_CONTROLS_URL}/schema")

    # Then: the schema is returned (header is ignored, route is public)
    assert resp.status_code == 200, resp.text


def test_schema_endpoint_reachable_with_non_admin_key(
    non_admin_client: TestClient,
) -> None:
    # Given: a non-admin client
    # When: the schema endpoint is fetched
    resp = non_admin_client.get(f"{_CONTROLS_URL}/schema")

    # Then: the schema is returned
    assert resp.status_code == 200, resp.text


def test_schema_endpoint_openapi_is_public(client: TestClient) -> None:
    schema = client.app.openapi()

    operation = schema["paths"][f"{_CONTROLS_URL}/schema"]["get"]
    assert operation.get("security") == []


# ---------------------------------------------------------------------------
# CONTROLS_READ operations: AUTHENTICATED suffices.
# ---------------------------------------------------------------------------


def test_non_admin_can_list_controls(
    non_admin_client: TestClient, client: TestClient
) -> None:
    # Given: an existing control
    _create_control(client)

    # When: a non-admin lists controls
    resp = non_admin_client.get(_CONTROLS_URL)

    # Then: the list is returned
    assert resp.status_code == 200, resp.text


def test_non_admin_can_get_control(
    non_admin_client: TestClient, client: TestClient
) -> None:
    # Given: an existing control
    control_id = _create_control(client)

    # When: a non-admin reads it
    resp = non_admin_client.get(f"{_CONTROLS_URL}/{control_id}")

    # Then: the control is returned
    assert resp.status_code == 200, resp.text


def test_non_admin_can_get_control_data(
    non_admin_client: TestClient, client: TestClient
) -> None:
    # Given: an existing control
    control_id = _create_control(client)

    # When: a non-admin reads its data
    resp = non_admin_client.get(f"{_CONTROLS_URL}/{control_id}/data")

    # Then: the data is returned
    assert resp.status_code == 200, resp.text


def test_non_admin_can_list_versions(
    non_admin_client: TestClient, client: TestClient
) -> None:
    # Given: an existing control with at least one version (creation)
    control_id = _create_control(client)

    # When: a non-admin lists versions
    resp = non_admin_client.get(f"{_CONTROLS_URL}/{control_id}/versions")

    # Then: the version list is returned
    assert resp.status_code == 200, resp.text


def test_non_admin_can_get_specific_version(
    non_admin_client: TestClient, client: TestClient
) -> None:
    # Given: an existing control (version 1 = "created")
    control_id = _create_control(client)

    # When: a non-admin reads version 1
    resp = non_admin_client.get(f"{_CONTROLS_URL}/{control_id}/versions/1")

    # Then: the version snapshot is returned
    assert resp.status_code == 200, resp.text


