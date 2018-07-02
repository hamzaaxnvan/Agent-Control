from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_control_evaluators import RegexEvaluatorConfig
from agent_control_models import ConditionNode
from agent_control_models.errors import ErrorCode
from agent_control_server.auth_framework import Operation, Principal, set_authorizer
from agent_control_server.db import get_async_db
from agent_control_server.endpoints import controls as controls_module
from agent_control_server.errors import BadRequestError, ForbiddenError
from agent_control_server.main import app
from agent_control_server.models import (
    DEFAULT_NAMESPACE_KEY,
    Control,
    ControlBinding,
    ControlVersion,
)
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .conftest import engine
from .utils import VALID_CONTROL_PAYLOAD


def _make_integrity_error(constraint_name: str) -> IntegrityError:
    diag = SimpleNamespace(constraint_name=constraint_name)
    orig = Exception(f'duplicate key value violates unique constraint "{constraint_name}"')
    setattr(orig, "diag", diag)
    return IntegrityError("statement", {}, orig)


def _create_control(
    client: TestClient,
    name: str | None = None,
    data: dict | None = None,
) -> tuple[int, str]:
    control_name = name or f"control-{uuid.uuid4()}"
    payload = deepcopy(data) if data is not None else deepcopy(VALID_CONTROL_PAYLOAD)
    resp = client.put("/api/v1/controls", json={"name": control_name, "data": payload})
    assert resp.status_code == 200
    return resp.json()["control_id"], control_name


def _insert_unconfigured_control(name: str | None = None) -> tuple[int, str]:
    control_name = name or f"control-{uuid.uuid4()}"
    control = Control(name=control_name, data={})
    with Session(engine) as session:
        session.add(control)
        session.commit()
        session.refresh(control)
        return int(control.id), control_name


def _set_control_data(client: TestClient, control_id: int, data: dict) -> None:
    resp = client.put(f"/api/v1/controls/{control_id}/data", json={"data": data})
    assert resp.status_code == 200, resp.text


def test_clone_and_bind_creates_cloned_control_binding_and_version(
    client: TestClient,
) -> None:
    source_id, source_name = _create_control(client)

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-123",
                "enabled": False,
            }
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    clone_id = body["id"]
    binding_id = body["binding_id"]
    assert clone_id != source_id
    assert body["name"].startswith(f"{source_name}-clone-")
    assert body["cloned_from_control_id"] == source_id

    with Session(engine) as session:
        source = session.get_one(Control, source_id)
        clone = session.get_one(Control, clone_id)
        binding = session.execute(
            select(ControlBinding).where(ControlBinding.id == binding_id)
        ).scalar_one()
        version = session.execute(
            select(ControlVersion).where(ControlVersion.control_id == clone_id)
        ).scalar_one()

    assert clone.namespace_key == source.namespace_key
    assert clone.data == source.data
    assert clone.cloned_from_control_id == source_id
    assert binding.control_id == clone_id
    assert binding.target_type == "log_stream"
    assert binding.target_id == "logstream-123"
    assert binding.enabled is False
    assert version.version_num == 1
    assert version.event_type == "cloned"
    assert version.note == f"Cloned from control {source_id}"
    assert version.snapshot["cloned_from_control_id"] == source_id
    assert version.snapshot["cloned_control_id"] == source_id

    get_resp = client.get(f"/api/v1/controls/{clone_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["cloned_from_control_id"] == source_id


def test_control_clone_lineage_enforces_same_namespace() -> None:
    source = Control(
        namespace_key=DEFAULT_NAMESPACE_KEY,
        name=f"source-{uuid.uuid4()}",
        data=deepcopy(VALID_CONTROL_PAYLOAD),
    )
    clone = Control(
        namespace_key="other-namespace",
        name=f"clone-{uuid.uuid4()}",
        data=deepcopy(VALID_CONTROL_PAYLOAD),
        cloned_from_control_id=1,
    )

    with Session(engine) as session:
        session.add(source)
        session.flush()
        clone.cloned_from_control_id = int(source.id)
        session.add(clone)
        with pytest.raises(IntegrityError):
            session.commit()


def test_clone_and_bind_generated_name_falls_back_for_legacy_name(
    client: TestClient,
) -> None:
    legacy_name = "legacy control name"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO controls (name, data) VALUES (:name, CAST(:data AS JSONB))"
            ),
            {
                "name": legacy_name,
                "data": json.dumps(VALID_CONTROL_PAYLOAD),
            },
        )
        row = conn.execute(
            text("SELECT id FROM controls WHERE name = :name"),
            {"name": legacy_name},
        ).fetchone()
        assert row is not None
        source_id = row[0]

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-legacy-name",
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["name"].startswith(f"control-{source_id}-clone-")


def test_list_controls_filters_by_cloned_state(client: TestClient) -> None:
    source_id, _ = _create_control(client, name=f"Root-{uuid.uuid4()}")
    clone_name = f"Clone-{uuid.uuid4()}"
    clone_resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "name": clone_name,
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-456",
            },
        },
    )
    assert clone_resp.status_code == 200, clone_resp.text
    clone_id = clone_resp.json()["id"]

    root_resp = client.get("/api/v1/controls", params={"cloned": False, "limit": 100})
    assert root_resp.status_code == 200
    root_ids = {control["id"] for control in root_resp.json()["controls"]}
    assert source_id in root_ids
    assert clone_id not in root_ids

    clone_list_resp = client.get(
        "/api/v1/controls", params={"cloned": True, "limit": 100}
    )
    assert clone_list_resp.status_code == 200
    cloned_controls = clone_list_resp.json()["controls"]
    cloned_ids = {control["id"] for control in cloned_controls}
    assert clone_id in cloned_ids
    assert source_id not in cloned_ids
    listed_clone = next(control for control in cloned_controls if control["id"] == clone_id)
    assert listed_clone["cloned_from_control_id"] == source_id


def test_clone_and_bind_returns_conflict_for_duplicate_clone_name(
    client: TestClient,
) -> None:
    _, existing_name = _create_control(client)
    source_id, _ = _create_control(client)

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "name": existing_name,
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-789",
            },
        },
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONTROL_NAME_CONFLICT"


def test_clone_and_bind_integrity_error_name_conflict_returns_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id, _ = _create_control(client)

    async def fail_create_version(
        self: controls_module.ControlService,
        control: Control,
        *,
        event_type: str,
        note: str,
    ) -> None:
        _ = (self, control, event_type, note)
        raise _make_integrity_error("idx_controls_namespace_name_active")

    monkeypatch.setattr(
        controls_module.ControlService,
        "create_version",
        fail_create_version,
    )

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "name": f"race-{uuid.uuid4()}",
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-race",
            },
        },
    )

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONTROL_NAME_CONFLICT"


def test_clone_and_bind_generated_name_retries_preflight_conflicts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id, source_name = _create_control(client, name=f"source-{uuid.uuid4()}")
    first_suffix = "1111111111111111"
    second_suffix = "2222222222222222"
    _create_control(client, name=f"{source_name}-clone-{first_suffix}")
    suffixes = iter([first_suffix, second_suffix])

    def fake_uuid4() -> SimpleNamespace:
        return SimpleNamespace(hex=next(suffixes))

    monkeypatch.setattr(controls_module.uuid, "uuid4", fake_uuid4)

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-retry-name",
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == f"{source_name}-clone-{second_suffix}"


def test_clone_and_bind_rolls_back_clone_when_binding_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id, _ = _create_control(client)
    clone_name = f"CloneRollback-{uuid.uuid4()}"

    async def fail_create_binding(*args: Any, **kwargs: Any) -> None:
        raise BadRequestError(
            error_code=ErrorCode.CONTROL_BINDING_INCOMPATIBLE,
            detail="Binding failed after clone creation.",
            resource="ControlBinding",
        )

    monkeypatch.setattr(
        controls_module.ControlBindingsService,
        "create_binding",
        fail_create_binding,
    )

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "name": clone_name,
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-rollback",
            },
        },
    )

    assert resp.status_code == 400
    with Session(engine) as session:
        clone = session.execute(
            select(Control).where(Control.name == clone_name)
        ).scalar_one_or_none()
    assert clone is None


def test_clone_and_bind_locks_source_control(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id, _ = _create_control(client)
    original_get_active = controls_module.ControlService.get_active_control_or_404
    seen_for_update: list[bool] = []

    async def recording_get_active(
        self: controls_module.ControlService,
        control_id_arg: int,
        *,
        namespace_key: str | None = None,
        for_update: bool = False,
    ) -> Control:
        seen_for_update.append(for_update)
        return await original_get_active(
            self,
            control_id_arg,
            namespace_key=namespace_key,
            for_update=for_update,
        )

    monkeypatch.setattr(
        controls_module.ControlService,
        "get_active_control_or_404",
        recording_get_active,
    )

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-lock",
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert seen_for_update == [True]


def test_clone_and_bind_rejects_auth_namespace_mismatch(client: TestClient) -> None:
    source_id, _ = _create_control(client)

    class MismatchedNamespaceAuthorizer:
        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            namespace_key = (
                "other-namespace"
                if operation == Operation.CONTROL_BINDINGS_WRITE
                else DEFAULT_NAMESPACE_KEY
            )
            return Principal(namespace_key=namespace_key, is_admin=True)

    set_authorizer(MismatchedNamespaceAuthorizer())

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-mismatch",
            },
        },
    )

    assert resp.status_code == 403
    assert resp.json()["error_code"] == "AUTH_INSUFFICIENT_PRIVILEGES"


def test_clone_and_bind_requires_source_read_authorization(
    client: TestClient,
) -> None:
    source_id, _ = _create_control(client)
    calls: list[tuple[Operation, dict[str, Any] | None]] = []

    class ReadMismatchAuthorizer:
        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            calls.append((operation, context))
            namespace_key = (
                "other-namespace"
                if operation == Operation.CONTROLS_READ
                else DEFAULT_NAMESPACE_KEY
            )
            return Principal(namespace_key=namespace_key, is_admin=True)

    set_authorizer(ReadMismatchAuthorizer())

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-read-auth",
            },
        },
    )

    assert resp.status_code == 403
    assert resp.json()["error_code"] == "AUTH_INSUFFICIENT_PRIVILEGES"
    read_contexts = [
        context for operation, context in calls if operation == Operation.CONTROLS_READ
    ]
    assert read_contexts == [None]


def test_clone_and_bind_context_tolerates_invalid_body_shapes(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/v1/controls/1/clone-and-bind",
        content="{",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422

    list_resp = client.post("/api/v1/controls/1/clone-and-bind", json=[])
    assert list_resp.status_code == 422

    bad_target_resp = client.post(
        "/api/v1/controls/1/clone-and-bind",
        json={"target_binding": "not-an-object"},
    )
    assert bad_target_resp.status_code == 422


def test_clone_and_bind_context_drops_invalid_target_fields(
    client: TestClient,
) -> None:
    calls: list[tuple[Operation, dict[str, Any] | None]] = []

    class RecordingAuthorizer:
        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            calls.append((operation, context))
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY, is_admin=True)

    set_authorizer(RecordingAuthorizer())

    resp = client.post(
        "/api/v1/controls/1/clone-and-bind",
        json={
            "target_binding": {
                "target_type": ["log_stream"],
                "target_id": {"id": "logstream-invalid"},
            },
        },
    )

    assert resp.status_code == 422
    binding_contexts = [
        context
        for operation, context in calls
        if operation == Operation.CONTROL_BINDINGS_WRITE
    ]
    assert binding_contexts == [{}]


def test_clone_and_bind_context_drops_overlong_target_fields(
    client: TestClient,
) -> None:
    calls: list[tuple[Operation, dict[str, Any] | None]] = []

    class RecordingAuthorizer:
        async def authorize(
            self,
            request: Any,
            operation: Operation,
            context: dict[str, Any] | None = None,
        ) -> Principal:
            calls.append((operation, context))
            return Principal(namespace_key=DEFAULT_NAMESPACE_KEY, is_admin=True)

    set_authorizer(RecordingAuthorizer())

    resp = client.post(
        "/api/v1/controls/1/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "x" * 256,
                "target_id": "logstream-invalid",
            },
        },
    )

    assert resp.status_code == 422
    binding_contexts = [
        context
        for operation, context in calls
        if operation == Operation.CONTROL_BINDINGS_WRITE
    ]
    assert binding_contexts == [{}]


def test_clone_and_bind_rejects_unknown_target_binding_fields(
    client: TestClient,
) -> None:
    source_id, _ = _create_control(client)

    resp = client.post(
        f"/api/v1/controls/{source_id}/clone-and-bind",
        json={
            "target_binding": {
                "target_type": "log_stream",
                "target_id": "logstream-extra",
                "unknown_field": "ignored-before",
            },
        },
    )

    assert resp.status_code == 422


@pytest.mark.parametrize(
    "constraint_name",
    ["idx_controls_name_active", "idx_controls_namespace_name_active"],
)
def test_create_control_integrity_error_returns_conflict(
    client: TestClient, constraint_name: str
) -> None:
    """DB uniqueness violations during create should be surfaced as 409 conflicts."""

    async def mock_db_integrity_error() -> AsyncGenerator[AsyncSession, None]:
        mock_session = AsyncMock(spec=AsyncSession)
        existing_result = MagicMock()
        existing_result.first.return_value = None

        mock_session.execute = AsyncMock(return_value=existing_result)
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock()
        mock_session.commit = AsyncMock(
            side_effect=_make_integrity_error(constraint_name)
        )
        yield mock_session

    app.dependency_overrides[get_async_db] = mock_db_integrity_error
    try:
        resp = client.put(
            "/api/v1/controls",
            json={"name": "duplicate-control", "data": VALID_CONTROL_PAYLOAD},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONTROL_NAME_CONFLICT"


@pytest.mark.parametrize(
    "constraint_name",
    ["idx_controls_name_active", "idx_controls_namespace_name_active"],
)
def test_patch_control_rename_integrity_error_returns_conflict(
    client: TestClient, constraint_name: str
) -> None:
    """DB uniqueness violations during rename should be surfaced as 409 conflicts."""
    control_obj = SimpleNamespace(
        id=1,
        name="old-control",
        data=deepcopy(VALID_CONTROL_PAYLOAD),
        deleted_at=None,
    )

    async def mock_db_integrity_error() -> AsyncGenerator[AsyncSession, None]:
        mock_session = AsyncMock(spec=AsyncSession)

        control_lookup_result = MagicMock()
        control_lookup_result.scalars.return_value.first.return_value = control_obj

        name_lookup_result = MagicMock()
        name_lookup_result.first.return_value = None

        lock_result = MagicMock()
        version_lookup_result = MagicMock()
        version_lookup_result.scalar_one.return_value = 1

        mock_session.execute = AsyncMock(
            side_effect=[
                control_lookup_result,
                name_lookup_result,
                lock_result,
                version_lookup_result,
            ]
        )
        mock_session.commit = AsyncMock(
            side_effect=_make_integrity_error(constraint_name)
        )
        yield mock_session

    app.dependency_overrides[get_async_db] = mock_db_integrity_error
    try:
        resp = client.patch("/api/v1/controls/1", json={"name": "existing-control"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONTROL_NAME_CONFLICT"


def test_patch_control_non_name_integrity_error_returns_500(client: TestClient) -> None:
    """Non-name integrity failures during patch should surface as database errors."""
    control_obj = SimpleNamespace(
        id=1,
        name="old-control",
        data=deepcopy(VALID_CONTROL_PAYLOAD),
        deleted_at=None,
    )

    async def mock_db_integrity_error() -> AsyncGenerator[AsyncSession, None]:
        mock_session = AsyncMock(spec=AsyncSession)

        control_lookup_result = MagicMock()
        control_lookup_result.scalars.return_value.first.return_value = control_obj

        lock_result = MagicMock()
        version_lookup_result = MagicMock()
        version_lookup_result.scalar_one.return_value = 1

        mock_session.execute = AsyncMock(
            side_effect=[
                control_lookup_result,
                lock_result,
                version_lookup_result,
            ]
        )
        mock_session.commit = AsyncMock(
            side_effect=_make_integrity_error("uq_control_versions_control_version")
        )
        yield mock_session

    app.dependency_overrides[get_async_db] = mock_db_integrity_error
    try:
        resp = client.patch("/api/v1/controls/1", json={"enabled": False})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500
    assert resp.json()["error_code"] == "DATABASE_ERROR"


def test_list_controls_filters_and_pagination(client: TestClient) -> None:
    # Given: three controls with varying data
    control1_id, control1_name = _create_control(client, name=f"AlphaControl-{uuid.uuid4()}")
    control2_id, control2_name = _create_control(client, name=f"BetaControl-{uuid.uuid4()}")
    control3_id, control3_name = _create_control(client, name=f"GammaControl-{uuid.uuid4()}")

    data1 = deepcopy(VALID_CONTROL_PAYLOAD)
    data1.update(
        {
            "description": "alpha",
            "enabled": True,
            "execution": "server",
            "scope": {"step_types": ["tool"], "stages": ["pre"]},
            "tags": ["pci"],
        }
    )

    data2 = deepcopy(VALID_CONTROL_PAYLOAD)
    data2.update(
        {
            "description": "beta",
            "enabled": False,
            "execution": "server",
            "scope": {"step_types": ["llm"], "stages": ["post"]},
            "tags": ["hipaa"],
        }
    )

    data3 = deepcopy(VALID_CONTROL_PAYLOAD)
    data3.pop("enabled", None)
    data3.pop("scope", None)
    data3.update({"description": "gamma", "tags": ["misc"]})

    _set_control_data(client, control1_id, data1)
    _set_control_data(client, control2_id, data2)
    _set_control_data(client, control3_id, data3)

    # When: filtering by name (case-insensitive partial match)
    resp = client.get("/api/v1/controls", params={"name": "alpha"})
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["controls"]]
    # Then: only the matching control is returned
    assert names == [control1_name]

    # When: filtering by enabled=false
    resp = client.get("/api/v1/controls", params={"enabled": "false"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}
    # Then: only explicitly disabled controls are returned
    assert names == {control2_name}

    # When: filtering by step_type=tool (controls without scope still match)
    resp = client.get("/api/v1/controls", params={"step_type": "tool"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}
    # Then: controls with matching step_type or missing scope are included
    assert control1_name in names
    assert control3_name in names
    assert control2_name not in names

    # When: filtering by tag
    resp = client.get("/api/v1/controls", params={"tag": "pci"})
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["controls"]]
    # Then: only controls with the tag are returned
    assert names == [control1_name]

    # Then: enabled defaults to True when missing
    resp = client.get("/api/v1/controls", params={"name": "gamma"})
    assert resp.status_code == 200
    control = resp.json()["controls"][0]
    assert control["name"] == control3_name
    assert control["enabled"] is True
    assert control["action"] == {"decision": "deny", "steering_context": None}

    # When: paginating
    resp = client.get("/api/v1/controls", params={"limit": 1})
    assert resp.status_code == 200
    page1 = resp.json()
    # Then: response indicates more pages
    assert page1["pagination"]["has_more"] is True
    assert page1["pagination"]["next_cursor"] is not None
    first_id = page1["controls"][0]["id"]

    # When: fetching the next page
    resp2 = client.get(
        "/api/v1/controls",
        params={"limit": 1, "cursor": page1["pagination"]["next_cursor"]},
    )
    assert resp2.status_code == 200
    page2 = resp2.json()
    # Then: the next page has a different item
    assert page2["controls"][0]["id"] != first_id


def test_patch_control_enabled_with_invalid_data_returns_corrupted_data(
    client: TestClient,
) -> None:
    # Given: a control with an invalid empty payload
    control_id, _ = _insert_unconfigured_control()

    # When: toggling enabled
    resp = client.patch(f"/api/v1/controls/{control_id}", json={"enabled": False})

    # Then: corrupted-data validation is returned
    assert resp.status_code == 422
    data = resp.json()
    assert data["error_code"] == "CORRUPTED_DATA"


def test_patch_control_rename_conflict(client: TestClient) -> None:
    # Given: two controls
    _, existing_name = _create_control(client)
    control_id, _ = _create_control(client)

    # When: renaming to an existing name
    resp = client.patch(f"/api/v1/controls/{control_id}", json={"name": existing_name})

    # Then: conflict
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "CONTROL_NAME_CONFLICT"


def test_patch_control_rename_with_spaces_rejected(client: TestClient) -> None:
    # Given: an existing control
    control_id, _ = _create_control(client)

    # When: renaming with spaces in the name
    resp = client.patch(
        f"/api/v1/controls/{control_id}",
        json={"name": "control with spaces"},
    )

    # Then: request validation rejects the rename
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"


def test_create_control_trimmed_name_stored(client: TestClient) -> None:
    """Control names are canonicalized at the API boundary: leading/trailing whitespace is trimmed."""
    resp = client.put(
        "/api/v1/controls",
        json={"name": "  trimmed-control  ", "data": VALID_CONTROL_PAYLOAD},
    )
    assert resp.status_code == 200
    control_id = resp.json()["control_id"]
    get_resp = client.get(f"/api/v1/controls/{control_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "trimmed-control"


def test_patch_control_trimmed_name_stored(client: TestClient) -> None:
    """PATCH control name is canonicalized at the API boundary: leading/trailing whitespace is trimmed."""
    control_id, _ = _create_control(client)
    resp = client.patch(
        f"/api/v1/controls/{control_id}",
        json={"name": "  new-trimmed-name  "},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new-trimmed-name"


def test_patch_control_legacy_name_preserved_when_name_omitted(
    client: TestClient,
) -> None:
    """Controls with legacy names (e.g. created before slug validation) remain editable.

    Policy: existing invalid names stay as-is when the client does not send a name
    update. PATCH with only enabled or other fields must not change or re-validate
    the stored name.
    """
    # Insert a control with a legacy name that would not pass current SlugName validation.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO controls (name, data) VALUES (:name, CAST(:data AS JSONB))"
            ),
            {
                "name": "legacy control name",
                "data": json.dumps(VALID_CONTROL_PAYLOAD),
            },
        )
        row = conn.execute(
            text("SELECT id FROM controls WHERE name = 'legacy control name'")
        ).fetchone()
        assert row is not None
        control_id = row[0]

    # When: PATCH without sending name (no name update, no enabled change)
    resp = client.patch(
        f"/api/v1/controls/{control_id}",
        json={},
    )
    assert resp.status_code == 200
    # Then: stored name is unchanged
    assert resp.json()["name"] == "legacy control name"
    get_resp = client.get(f"/api/v1/controls/{control_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "legacy control name"


def test_list_controls_filters_stage_and_execution(client: TestClient) -> None:
    # Given: controls with differing stages and execution targets
    control1_id, control1_name = _create_control(client)
    control2_id, control2_name = _create_control(client)
    control3_id, control3_name = _create_control(client)

    data1 = deepcopy(VALID_CONTROL_PAYLOAD)
    data1.update(
        {
            "execution": "server",
            "scope": {"stages": ["pre"], "step_types": ["llm"]},
        }
    )
    data2 = deepcopy(VALID_CONTROL_PAYLOAD)
    data2.update(
        {
            "execution": "sdk",
            "scope": {"stages": ["post"], "step_types": ["llm"]},
        }
    )
    data3 = deepcopy(VALID_CONTROL_PAYLOAD)
    data3.update({"execution": "server"})
    data3.pop("scope", None)

    _set_control_data(client, control1_id, data1)
    _set_control_data(client, control2_id, data2)
    _set_control_data(client, control3_id, data3)

    # When: filtering by stage=pre
    resp = client.get("/api/v1/controls", params={"stage": "pre"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}
    # Then: matching stage and missing scope are included
    assert names == {control1_name, control3_name}

    # When: filtering by stage=post
    resp = client.get("/api/v1/controls", params={"stage": "post"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}
    # Then: matching stage and missing scope are included
    assert names == {control2_name, control3_name}

    # When: filtering by execution=server
    resp = client.get("/api/v1/controls", params={"execution": "server"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}
    # Then: only server-executed controls are returned
    assert names == {control1_name, control3_name}

    # When: filtering by execution=sdk
    resp = client.get("/api/v1/controls", params={"execution": "sdk"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}
    # Then: only sdk-executed controls are returned
    assert names == {control2_name}


def test_list_controls_combined_filters(client: TestClient) -> None:
    # Given: controls with distinct names/tags
    control1_id, control1_name = _create_control(client, name=f"Alpha-{uuid.uuid4()}")
    control2_id, control2_name = _create_control(client, name=f"Alpha-{uuid.uuid4()}")

    data1 = deepcopy(VALID_CONTROL_PAYLOAD)
    data1.update({"tags": ["pci"], "enabled": True})
    data2 = deepcopy(VALID_CONTROL_PAYLOAD)
    data2.update({"tags": ["hipaa"], "enabled": True})

    _set_control_data(client, control1_id, data1)
    _set_control_data(client, control2_id, data2)

    # When: filtering by name and tag together
    resp = client.get(
        "/api/v1/controls",
        params={"name": "alpha", "tag": "pci"},
    )
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["controls"]]

    # Then: only controls matching all filters are returned
    assert names == [control1_name]


def test_list_controls_enabled_true_includes_missing_enabled(client: TestClient) -> None:
    # Given: controls with enabled true, enabled false, and missing enabled
    control_true_id, control_true_name = _create_control(client, name=f"Enabled-{uuid.uuid4()}")
    control_false_id, control_false_name = _create_control(client, name=f"Disabled-{uuid.uuid4()}")
    control_missing_id, control_missing_name = _create_control(client, name=f"Missing-{uuid.uuid4()}")

    data_true = deepcopy(VALID_CONTROL_PAYLOAD)
    data_true["enabled"] = True
    data_false = deepcopy(VALID_CONTROL_PAYLOAD)
    data_false["enabled"] = False
    data_missing = deepcopy(VALID_CONTROL_PAYLOAD)
    data_missing.pop("enabled", None)

    _set_control_data(client, control_true_id, data_true)
    _set_control_data(client, control_false_id, data_false)
    _set_control_data(client, control_missing_id, data_missing)

    # When: filtering by enabled=true
    resp = client.get("/api/v1/controls", params={"enabled": "true"})
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["controls"]}

    # Then: enabled=true and missing enabled are included; enabled=false is excluded
    assert names == {control_true_name, control_missing_name}


def test_list_controls_cursor_with_tag_filter(client: TestClient) -> None:
    # Given: multiple controls sharing a tag and one without it
    control_ids = []
    control_names = []
    for _ in range(3):
        cid, name = _create_control(client, name=f"Tagged-{uuid.uuid4()}")
        control_ids.append(cid)
        control_names.append(name)

    other_id, other_name = _create_control(client, name=f"Other-{uuid.uuid4()}")

    data_tagged = deepcopy(VALID_CONTROL_PAYLOAD)
    data_tagged.update({"tags": ["pci"]})
    data_other = deepcopy(VALID_CONTROL_PAYLOAD)
    data_other.update({"tags": ["hipaa"]})

    for cid in control_ids:
        _set_control_data(client, cid, data_tagged)
    _set_control_data(client, other_id, data_other)

    # When: requesting the first page filtered by tag
    resp = client.get("/api/v1/controls", params={"tag": "pci", "limit": 2})
    assert resp.status_code == 200
    page1 = resp.json()

    # Then: pagination reflects filtered total and has more pages
    assert page1["pagination"]["total"] == 3
    assert page1["pagination"]["has_more"] is True
    assert page1["pagination"]["next_cursor"] is not None
    assert len(page1["controls"]) == 2
    assert all("pci" in c["tags"] for c in page1["controls"])

    # When: requesting the next page with cursor
    resp2 = client.get(
        "/api/v1/controls",
        params={"tag": "pci", "limit": 2, "cursor": page1["pagination"]["next_cursor"]},
    )
    assert resp2.status_code == 200
    page2 = resp2.json()
