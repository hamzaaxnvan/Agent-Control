import uuid
from copy import deepcopy
from typing import Any

from agent_control_server.models import Control
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from .conftest import engine


def create_control(client: TestClient, data: dict[str, Any] | None = None) -> int:
    name = f"control-{uuid.uuid4()}"
    payload = data if data is not None else VALID_CONTROL_DATA
    resp = client.put("/api/v1/controls", json={"name": name, "data": payload})
    assert resp.status_code == 200
    cid = resp.json()["control_id"]
    assert isinstance(cid, int)
    return cid


def create_unconfigured_control(name: str | None = None) -> int:
    control = Control(name=name or f"control-{uuid.uuid4()}", data={})
    with Session(engine) as session:
        session.add(control)
        session.commit()
        session.refresh(control)
        return int(control.id)


def test_create_control_returns_id(client: TestClient) -> None:
    # Given: no prior controls
    # When: creating a control via API
    resp = client.put(
        "/api/v1/controls",
        json={"name": f"control-{uuid.uuid4()}", "data": VALID_CONTROL_DATA},
    )
    # Then: a control_id is returned (integer)
    assert resp.status_code == 200
    assert isinstance(resp.json()["control_id"], int)


def test_create_control_with_data_stores_configured_payload(client: TestClient) -> None:
    # Given: a valid control payload included during create
    name = f"control-{uuid.uuid4()}"

    # When: creating the control with data in one request
    resp = client.put("/api/v1/controls", json={"name": name, "data": VALID_CONTROL_DATA})

    # Then: the control is created successfully
    assert resp.status_code == 200, resp.text
    control_id = resp.json()["control_id"]

    # When: reading back its data
    data_resp = client.get(f"/api/v1/controls/{control_id}/data")

    # Then: the configured payload was stored immediately
    assert data_resp.status_code == 200
    data = data_resp.json()["data"]
    assert data["description"] == VALID_CONTROL_DATA["description"]
    assert data["execution"] == VALID_CONTROL_DATA["execution"]
    assert data["condition"]["evaluator"] == VALID_CONTROL_DATA["condition"]["evaluator"]


def test_create_control_invalid_data_returns_422_without_persisting(client: TestClient) -> None:
    # Given: a create request whose control data fails evaluator validation
    name = f"control-{uuid.uuid4()}"
    invalid_data = deepcopy(VALID_CONTROL_DATA)
    invalid_data["condition"]["evaluator"] = {
        "name": "list",
        "config": {
            "values": ["a", "b"],
            "logic": "invalid_logic",
            "match_on": "match",
        },
    }

    # When: creating the control with invalid data
    resp = client.put("/api/v1/controls", json={"name": name, "data": invalid_data})

    # Then: the request is rejected
    assert resp.status_code == 422

    # And: no shell control was persisted
    list_resp = client.get("/api/v1/controls", params={"name": name})
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["pagination"]["total"] == 0
    assert body["controls"] == []


def test_create_control_without_data_returns_422(client: TestClient) -> None:
    resp = client.put("/api/v1/controls", json={"name": f"control-{uuid.uuid4()}"})
    assert resp.status_code == 422


def test_get_control_data_initially_unconfigured(client: TestClient) -> None:
    # Given: an invalid legacy control row with an empty payload
    control_id = create_unconfigured_control()
    # When: fetching its data
    resp = client.get(f"/api/v1/controls/{control_id}/data")
    # Then: 422 because empty data is invalid stored control data
    assert resp.status_code == 422
    response_data = resp.json()
    assert response_data["error_code"] == "CORRUPTED_DATA"
    assert "invalid data" in response_data.get("detail", "").lower()


def test_get_control_schema_returns_control_definition_schema(client: TestClient) -> None:
    resp = client.get("/api/v1/controls/schema")

    assert resp.status_code == 200, resp.text
    schema = resp.json()["schema"]
    properties = schema["properties"]

    assert schema["type"] == "object"
    assert {"execution", "condition", "action"}.issubset(properties)
    assert set(schema["required"]) >= {"execution", "condition", "action"}
    assert "condition" in properties
    assert "$defs" in schema


VALID_CONTROL_DATA = {
    "description": "Test Control",
    "enabled": True,
    "execution": "server",
    "scope": {"step_types": ["llm"], "stages": ["pre"]},
    "condition": {
        "selector": {"path": "input"},
        "evaluator": {
            "name": "regex",
            "config": {"pattern": "test", "flags": []}
        },
    },
    "action": {"decision": "deny"},
    "tags": ["test"]
}

def test_set_control_data_replaces_existing(client: TestClient) -> None:
    # Given: a legacy control with empty data
    control_id = create_unconfigured_control()
    # When: setting data
    payload = VALID_CONTROL_DATA
    resp_put = client.put(f"/api/v1/controls/{control_id}/data", json={"data": payload})
    # Then: update succeeds
    assert resp_put.status_code == 200, resp_put.text
    assert resp_put.json()["success"] is True

    # When: reading back
    resp_get = client.get(f"/api/v1/controls/{control_id}/data")
    # Then: data matches payload (with defaults filled in)
    assert resp_get.status_code == 200
    data = resp_get.json()["data"]
    # Core fields should match
    assert data["description"] == payload["description"]
    assert data["enabled"] == payload["enabled"]
    assert data["execution"] == payload["execution"]
    assert data["scope"] == payload["scope"]
    assert data["condition"]["evaluator"] == payload["condition"]["evaluator"]
    assert data["action"] == payload["action"]
    assert data["condition"]["selector"]["path"] == payload["condition"]["selector"]["path"]


def test_set_control_data_accepts_legacy_leaf_payload(client: TestClient) -> None:
    # Given: a legacy flat selector/evaluator payload
    control_id = create_control(client)
    payload = deepcopy(VALID_CONTROL_DATA)
    payload["selector"] = payload["condition"]["selector"]
    payload["evaluator"] = payload["condition"]["evaluator"]
    payload.pop("condition")

    # When: saving and reading back the control data
    resp_put = client.put(f"/api/v1/controls/{control_id}/data", json={"data": payload})

    # Then: the stored response is canonicalized into condition form
    assert resp_put.status_code == 200, resp_put.text
    resp_get = client.get(f"/api/v1/controls/{control_id}/data")
    assert resp_get.status_code == 200
    data = resp_get.json()["data"]
    assert "selector" not in data
    assert "evaluator" not in data
    assert data["condition"]["selector"]["path"] == "input"
    assert data["condition"]["evaluator"]["name"] == "regex"


def test_set_control_data_with_empty_dict_fails(client: TestClient) -> None:
    # Given: a control with non-empty data
    control_id = create_control(client)
    # When: setting empty dict
    resp_put = client.put(f"/api/v1/controls/{control_id}/data", json={"data": {}})
    # Then: Fails 422 because strict schema is enforced
    assert resp_put.status_code == 422

