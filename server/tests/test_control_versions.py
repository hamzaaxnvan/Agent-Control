from __future__ import annotations

import uuid
from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_control_server.models import ControlVersion

from .conftest import engine
from .utils import VALID_CONTROL_PAYLOAD


def _create_control(
    client: TestClient,
    *,
    name: str | None = None,
    data: dict[str, object] | None = None,
) -> tuple[int, str]:
    control_name = name or f"control-{uuid.uuid4()}"
    payload = deepcopy(data) if data is not None else deepcopy(VALID_CONTROL_PAYLOAD)
    resp = client.put("/api/v1/controls", json={"name": control_name, "data": payload})
    assert resp.status_code == 200, resp.text
    return resp.json()["control_id"], control_name


def _fetch_versions(control_id: int) -> list[ControlVersion]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(ControlVersion)
                .where(ControlVersion.control_id == control_id)
                .order_by(ControlVersion.version_num)
            ).all()
        )


def test_create_control_creates_initial_version_row(client: TestClient) -> None:
    # Given: a valid control create request
    control_id, control_name = _create_control(client)

    # When: inspecting persisted control versions
    versions = _fetch_versions(control_id)

    # Then: the control has a single initial version row
    assert len(versions) == 1
    version = versions[0]
    assert version.version_num == 1
    assert version.event_type == "created"
    assert version.note == "Initial creation"
    assert version.snapshot["name"] == control_name
    assert version.snapshot["data"]["description"] == VALID_CONTROL_PAYLOAD["description"]
    assert version.snapshot["deleted_at"] is None
    assert version.snapshot["cloned_from_control_id"] is None
    assert version.snapshot["cloned_control_id"] is None


def test_set_control_data_creates_edited_version_row(client: TestClient) -> None:
    # Given: an existing control
    control_id, _ = _create_control(client)
    updated_payload = deepcopy(VALID_CONTROL_PAYLOAD)
    updated_payload["description"] = "Updated description"

    # When: replacing the control data
    resp = client.put(f"/api/v1/controls/{control_id}/data", json={"data": updated_payload})

    # Then: a new edited version is recorded
    assert resp.status_code == 200, resp.text
    versions = _fetch_versions(control_id)
    assert [version.version_num for version in versions] == [1, 2]
    latest = versions[-1]
    assert latest.event_type == "updated"
    assert latest.note == "Edited"
    assert latest.snapshot["data"]["description"] == "Updated description"


def test_patch_control_creates_edited_version_row(client: TestClient) -> None:
    # Given: an existing control
    control_id, _ = _create_control(client)
    new_name = f"control-{uuid.uuid4()}"

    # When: renaming and disabling the control
    resp = client.patch(
