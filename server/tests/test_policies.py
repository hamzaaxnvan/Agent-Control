import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from agent_control_server.db import get_async_db
from agent_control_server.models import Control, Policy

from .utils import VALID_CONTROL_PAYLOAD


def _create_policy(client: TestClient) -> int:
    name = f"pol-{uuid.uuid4()}"
    r = client.put("/api/v1/policies", json={"name": name})
    assert r.status_code == 200
    return r.json()["policy_id"]


def _create_control(client: TestClient) -> int:
    name = f"ctrl-{uuid.uuid4()}"
    r = client.put("/api/v1/controls", json={"name": name, "data": VALID_CONTROL_PAYLOAD})
    assert r.status_code == 200
    return r.json()["control_id"]


def test_create_policy_and_duplicate_name(client: TestClient) -> None:
    # Given: a policy name
    name = f"pol-{uuid.uuid4()}"
    # When: creating the policy
    r1 = client.put("/api/v1/policies", json={"name": name})
    # Then: the policy is created with an id
    assert r1.status_code == 200
    assert isinstance(r1.json()["policy_id"], int)

    # When: creating the same policy name again
    r2 = client.put("/api/v1/policies", json={"name": name})
    # Then: a conflict is returned
    assert r2.status_code == 409


def test_policy_add_control_and_list(client: TestClient) -> None:
    # Given: a policy and a control
    policy_id = _create_policy(client)
    control_id = _create_control(client)

    # When: associating the control to the policy
    r = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    # Then: association succeeds
    assert r.status_code == 200
    assert r.json()["success"] is True

    # When: listing policy controls
    l = client.get(f"/api/v1/policies/{policy_id}/controls")
    # Then: the control id is included
    assert l.status_code == 200
    assert control_id in l.json()["control_ids"]


def test_policy_add_control_idempotent(client: TestClient) -> None:
    # Given: a policy with a control already associated
    policy_id = _create_policy(client)
    control_id = _create_control(client)
    client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")

    # When: adding the same control again
    r = client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    # Then: the request is still successful (idempotent)
    assert r.status_code == 200
    assert r.json()["success"] is True

    # Then: listing still shows it once (set semantics by ids)
    l = client.get(f"/api/v1/policies/{policy_id}/controls")
    assert l.status_code == 200
    ids = l.json()["control_ids"]
    assert ids.count(control_id) == 1


def test_policy_remove_control(client: TestClient) -> None:
    # Given: a policy with an associated control
    policy_id = _create_policy(client)
    control_id = _create_control(client)
    client.post(f"/api/v1/policies/{policy_id}/controls/{control_id}")

    # When: removing the association
    d = client.delete(f"/api/v1/policies/{policy_id}/controls/{control_id}")
    # Then: removal succeeds
    assert d.status_code == 200
    assert d.json()["success"] is True

    # When: listing controls
    l = client.get(f"/api/v1/policies/{policy_id}/controls")
    # Then: the control is not present
    assert l.status_code == 200
    assert control_id not in l.json()["control_ids"]


def test_policy_remove_control_idempotent_when_not_associated(client: TestClient) -> None:
    # Given: a policy and a control that are not associated
    policy_id = _create_policy(client)
    control_id = _create_control(client)

    # When: removing the association anyway
    resp = client.delete(f"/api/v1/policies/{policy_id}/controls/{control_id}")

    # Then: success is returned (idempotent)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Then: the control list remains empty
    list_resp = client.get(f"/api/v1/policies/{policy_id}/controls")
    assert list_resp.status_code == 200
    assert list_resp.json()["control_ids"] == []


def test_list_policy_controls_empty_for_new_policy(client: TestClient) -> None:
    # Given: a newly created policy with no controls
    policy_id = _create_policy(client)

    # When: listing policy controls
    resp = client.get(f"/api/v1/policies/{policy_id}/controls")

    # Then: an empty list is returned
    assert resp.status_code == 200
    assert resp.json()["control_ids"] == []


def test_policy_assoc_404s(client: TestClient) -> None:
    # Given: existing policy and control ids
    policy_id = _create_policy(client)
    control_id = _create_control(client)

