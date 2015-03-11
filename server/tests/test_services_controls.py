from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_control_models.errors import ErrorCode
from agent_control_server.errors import APIValidationError
from agent_control_server.models import (
    DEFAULT_NAMESPACE_KEY,
    Agent,
    Control,
    ControlBinding,
    ControlVersion,
    Policy,
    agent_controls,
    agent_policies,
    policy_controls,
)
from agent_control_server.services.controls import (
    ControlService,
)
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .conftest import AsyncSessionTest, engine
from .utils import VALID_CONTROL_PAYLOAD


def _unrendered_template_payload() -> dict[str, object]:
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
        "template_values": {},
    }


async def _create_versioned_control(
    *,
    name: str | None = None,
    data: dict[str, object] | None = None,
) -> tuple[int, str]:
    control_name = name or f"control-{uuid.uuid4()}"
    control_data = deepcopy(data) if data is not None else deepcopy(VALID_CONTROL_PAYLOAD)

    async with AsyncSessionTest() as session:
        service = ControlService(session)
        control = service.create_control(
            namespace_key=DEFAULT_NAMESPACE_KEY,
            name=control_name,
            data=control_data,
        )
        await service.create_version(
            control,
            event_type="created",
            note="Initial creation",
        )
        await session.commit()
        return control.id, control_name


def _fetch_control(control_id: int) -> Control | None:
    with Session(engine) as session:
        return session.scalars(select(Control).where(Control.id == control_id)).first()


def _fetch_control_by_name(name: str) -> Control | None:
    with Session(engine) as session:
        return session.scalars(select(Control).where(Control.name == name)).first()


def _fetch_versions(control_id: int) -> list[ControlVersion]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(ControlVersion)
                .where(ControlVersion.control_id == control_id)
                .order_by(ControlVersion.version_num)
            ).all()
        )


def _fetch_all_versions() -> list[ControlVersion]:
    with Session(engine) as session:
        return list(session.scalars(select(ControlVersion)).all())


@pytest.mark.asyncio
async def test_create_version_locks_control_row_before_allocating_version_number() -> None:
    # Given: a control service with a mocked session
    mock_session = AsyncMock(spec=AsyncSession)
    lock_result = MagicMock()
    version_lookup_result = MagicMock()
    version_lookup_result.scalar_one.return_value = 4
    mock_session.execute = AsyncMock(side_effect=[lock_result, version_lookup_result])
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    service = ControlService(mock_session)
    control = Control(
        id=123,
        name=f"control-{uuid.uuid4()}",
        data=VALID_CONTROL_PAYLOAD,
        deleted_at=None,
    )

    # When: creating a new version row
    version = await service.create_version(control, event_type="updated", note="Edited")

    # Then: the service first takes a row-level lock on the control
    lock_stmt = mock_session.execute.await_args_list[0].args[0]
    assert getattr(lock_stmt, "_for_update_arg", None) is not None

    # And: the allocated version number comes from the subsequent query
    assert version.version_num == 4


@pytest.mark.asyncio
async def test_create_control_transaction_rollback_does_not_persist_control_or_version() -> None:
    # Given: a new control plus its initial version inside an open transaction
    control_name = f"control-{uuid.uuid4()}"
    async with AsyncSessionTest() as session:
        service = ControlService(session)
        control = service.create_control(
            namespace_key=DEFAULT_NAMESPACE_KEY,
            name=control_name,
            data=deepcopy(VALID_CONTROL_PAYLOAD),
        )
        await service.create_version(
            control,
            event_type="created",
            note="Initial creation",
        )

        # When: the transaction is rolled back before commit
        await session.rollback()

    # Then: neither the control row nor the version row persist
    assert _fetch_control_by_name(control_name) is None
    assert _fetch_all_versions() == []


@pytest.mark.asyncio
async def test_replace_control_data_transaction_rollback_preserves_prior_state() -> None:
    # Given: a committed control with an initial version row
    control_id, _ = await _create_versioned_control()

    async with AsyncSessionTest() as session:
        service = ControlService(session)
        control = await service.get_active_control_or_404(
            control_id,
            namespace_key=DEFAULT_NAMESPACE_KEY,
        )
        updated_data = deepcopy(control.data)
        updated_data["description"] = "Should not persist"
        service.replace_control_data(control, data=updated_data)
        await service.create_version(
            control,
            event_type="updated",
            note="Edited",
        )

        # When: the edit transaction is rolled back
        await session.rollback()

    # Then: the persisted control state and version history remain unchanged
    persisted_control = _fetch_control(control_id)
    assert persisted_control is not None
    assert persisted_control.data["description"] == VALID_CONTROL_PAYLOAD["description"]
    assert [version.version_num for version in _fetch_versions(control_id)] == [1]


@pytest.mark.asyncio
async def test_patch_mutation_transaction_rollback_preserves_prior_state() -> None:
    # Given: a committed control with an initial version row
    control_id, control_name = await _create_versioned_control()

    async with AsyncSessionTest() as session:
        service = ControlService(session)
        control = await service.get_active_control_or_404(
            control_id,
            namespace_key=DEFAULT_NAMESPACE_KEY,
        )
        service.rename_control(control, name=f"{control_name}-renamed")
        service.set_control_enabled(control, enabled=False)
        await service.create_version(
            control,
            event_type="updated",
            note="Edited",
        )

        # When: the patch transaction is rolled back
        await session.rollback()

    # Then: the persisted control row and version history stay at the pre-patch state
    persisted_control = _fetch_control(control_id)
    assert persisted_control is not None
    assert persisted_control.name == control_name
    assert persisted_control.data["enabled"] is True
    assert [version.version_num for version in _fetch_versions(control_id)] == [1]


@pytest.mark.asyncio
async def test_delete_control_transaction_rollback_preserves_active_state() -> None:
    # Given: a committed control with an initial version row
    control_id, _ = await _create_versioned_control()

    async with AsyncSessionTest() as session:
        service = ControlService(session)
        control = await service.get_active_control_or_404(
            control_id,
            namespace_key=DEFAULT_NAMESPACE_KEY,
        )
        service.mark_control_deleted(control, deleted_at=dt.datetime.now(dt.UTC))
        await service.create_version(
            control,
            event_type="deleted",
            note="Deleted",
        )

        # When: the delete transaction is rolled back
        await session.rollback()

    # Then: the control remains active and no deleted version is persisted
    persisted_control = _fetch_control(control_id)
    assert persisted_control is not None
    assert persisted_control.deleted_at is None
    assert [version.version_num for version in _fetch_versions(control_id)] == [1]


@pytest.mark.asyncio
async def test_list_controls_for_policy_returns_controls(async_db) -> None:
    # Given: a policy with two associated controls
    policy = Policy(name=f"policy-{uuid.uuid4()}")
    control_a = Control(name=f"control-{uuid.uuid4()}", data=VALID_CONTROL_PAYLOAD)
    control_b = Control(name=f"control-{uuid.uuid4()}", data=VALID_CONTROL_PAYLOAD)
    async_db.add_all([policy, control_a, control_b])
    await async_db.flush()

    await async_db.execute(
        insert(policy_controls).values(
            [
                {"policy_id": policy.id, "control_id": control_a.id},
                {"policy_id": policy.id, "control_id": control_b.id},
            ]
        )
    )
    await async_db.commit()

    # When: listing controls for the policy
    controls = await ControlService(async_db).list_controls_for_policy(policy.id)

    # Then: both controls are returned
    names = {c.name for c in controls}
    assert names == {control_a.name, control_b.name}


@pytest.mark.asyncio
async def test_list_controls_for_policy_excludes_deleted_controls(async_db) -> None:
    # Given: a policy associated with one active and one soft-deleted control
    policy = Policy(name=f"policy-{uuid.uuid4()}")
    active_control = Control(name=f"control-{uuid.uuid4()}", data=VALID_CONTROL_PAYLOAD)
    deleted_control = Control(
        name=f"deleted-control-{uuid.uuid4()}",
        data=VALID_CONTROL_PAYLOAD,
        deleted_at=dt.datetime.now(dt.UTC),
    )
    async_db.add_all([policy, active_control, deleted_control])
    await async_db.flush()

    await async_db.execute(
        insert(policy_controls).values(
            [
                {"policy_id": policy.id, "control_id": active_control.id},
                {"policy_id": policy.id, "control_id": deleted_control.id},
            ]
        )
    )
    await async_db.commit()

    # When: listing controls for the policy
    controls = await ControlService(async_db).list_controls_for_policy(policy.id)

    # Then: only active controls are returned
    assert [control.id for control in controls] == [active_control.id]


@pytest.mark.asyncio
async def test_list_controls_for_agent_returns_controls(async_db) -> None:
    # Given: an agent associated with one policy control and one direct control
    policy = Policy(name=f"policy-{uuid.uuid4()}")
    policy_control = Control(name=f"policy-control-{uuid.uuid4()}", data=VALID_CONTROL_PAYLOAD)
    direct_control = Control(name=f"direct-control-{uuid.uuid4()}", data=VALID_CONTROL_PAYLOAD)
    agent = Agent(
        name=f"agent-{uuid.uuid4()}",
        data={},
    )
    async_db.add_all([policy, policy_control, direct_control, agent])
    await async_db.flush()

    await async_db.execute(
        insert(agent_policies).values({"agent_name": agent.name, "policy_id": policy.id})
    )
    await async_db.execute(
        insert(policy_controls).values({"policy_id": policy.id, "control_id": policy_control.id})
    )
    await async_db.execute(
        insert(agent_controls).values({"agent_name": agent.name, "control_id": direct_control.id})
    )
    await async_db.commit()

    # When: listing controls for the agent
    controls = await ControlService(async_db).list_controls_for_agent(
        agent.name, namespace_key=DEFAULT_NAMESPACE_KEY
    )

    # Then: both policy-derived and direct controls are returned
    assert len(controls) == 2
    names = {control.name for control in controls}
    assert names == {policy_control.name, direct_control.name}
    ids = [control.id for control in controls]
    assert ids == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_list_controls_for_agent_excludes_deleted_controls(async_db) -> None:
    # Given: an agent associated with one active and one soft-deleted control
    active_control = Control(name=f"active-control-{uuid.uuid4()}", data=VALID_CONTROL_PAYLOAD)
    deleted_control = Control(
        name=f"deleted-control-{uuid.uuid4()}",
        data=VALID_CONTROL_PAYLOAD,
        deleted_at=dt.datetime.now(dt.UTC),
    )
    agent = Agent(name=f"agent-{uuid.uuid4()}", data={})
    async_db.add_all([active_control, deleted_control, agent])
    await async_db.flush()

    await async_db.execute(
        insert(agent_controls).values(
