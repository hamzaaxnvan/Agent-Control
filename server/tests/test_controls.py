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


