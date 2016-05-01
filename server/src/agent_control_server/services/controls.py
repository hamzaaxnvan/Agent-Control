from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from agent_control_models import (
    ControlDefinition,
    ControlDefinitionRuntime,
    UnrenderedTemplateControl,
)
from agent_control_models.errors import ErrorCode, ValidationErrorItem
from agent_control_models.policy import Control as APIControl
from pydantic import ValidationError
from sqlalchemy import Integer, String, delete, exists, func, literal, or_, select, union, union_all
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from ..errors import APIValidationError, NotFoundError
from ..models import (
    Control,
    ControlBinding,
    ControlVersion,
    agent_controls,
    agent_policies,
    policy_controls,
)
from .control_definitions import (
    parse_control_definition_or_api_error,
    parse_runtime_control_definition_or_api_error,
)
from .query_utils import escape_like_pattern

type AgentControlRenderedState = Literal["rendered", "unrendered", "all"]
type AgentControlEnabledState = Literal["enabled", "disabled", "all"]

_MAX_INLINE_TARGET_ATTACHMENTS_PER_CONTROL = 20


@dataclass(frozen=True)
class RuntimeControl:
    """Internal runtime control payload for evaluation hot paths."""

    id: int
    name: str
    control: ControlDefinitionRuntime


@dataclass(frozen=True)
class ControlVersionPage:
    """Paginated control-version results."""

    versions: list[ControlVersion]
    total: int
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True)
class ControlListPage:
    """Paginated control rows for browse/list endpoints."""

    controls: list[Control]
    total: int
    has_more: bool
    next_cursor: str | None


@dataclass(frozen=True)
class ControlUsage:
    """Usage attribution summary for a listed control."""

    representative_agent_name: str | None
    used_by_agents_count: int


@dataclass(frozen=True)
class ControlTargetAttachment:
    """Target binding attached to a control."""

    binding_id: int
    target_type: str
    target_id: str
    enabled: bool


@dataclass(frozen=True)
class ControlAttachmentSet:
    """Direct attachments for a listed control."""

    policy_ids: list[int]
    agent_names: list[str]
    targets: list[ControlTargetAttachment]
    targets_total: int
    targets_truncated: bool


@dataclass(frozen=True)
class ControlAssociations:
    """Policy and agent associations for a control."""

    policy_ids: list[int]
    agent_names: list[str]


@dataclass(frozen=True)
class RemoveAgentControlResult:
    """Outcome for removing a direct control association from an agent."""

    removed_direct_association: bool
    control_still_active: bool


class ControlService:
    """Shared control persistence helpers used by server endpoints."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def create_control(
        self,
        *,
        namespace_key: str,
        name: str,
        data: dict[str, Any],
        cloned_from_control_id: int | None = None,
        seed_source_id: str | None = None,
    ) -> Control:
        """Create a new pending control row."""
        control = Control(
            namespace_key=namespace_key,
            name=name,
            data=data,
            cloned_from_control_id=cloned_from_control_id,
            seed_source_id=seed_source_id,
        )
        self._db.add(control)
        return control

    @staticmethod
    def rename_control(control: Control, *, name: str) -> None:
        """Update a control name in-memory before commit."""
        control.name = name

    @staticmethod
    def replace_control_data(control: Control, *, data: dict[str, Any]) -> None:
        """Replace the stored JSON payload for a control."""
        control.data = data

    @staticmethod
    def set_control_enabled(control: Control, *, enabled: bool) -> None:
        """Persist a new enabled flag on an existing control payload."""
        updated_data = dict(control.data)
        updated_data["enabled"] = enabled
        control.data = updated_data

    @staticmethod
    def mark_control_deleted(control: Control, *, deleted_at: dt.datetime) -> None:
        """Mark a control as soft-deleted."""
        control.deleted_at = deleted_at
        if control.seed_source_id is not None:
            control.seed_opted_out_at = deleted_at

    async def seed_source_exists(
        self,
        seed_source_id: str,
        *,
        namespace_key: str,
    ) -> bool:
        """Return whether a control has claimed an immutable seed identity."""
        stmt = select(Control.id).where(
            Control.namespace_key == namespace_key,
            Control.seed_source_id == seed_source_id,
        )
        result = await self._db.execute(stmt)
        return result.first() is not None

    async def get_control_or_404(
        self,
        control_id: int,
        *,
        namespace_key: str,
        for_update: bool = False,
    ) -> Control:
        """Load any control row, including soft-deleted controls."""
        stmt = select(Control).where(
            Control.id == control_id,
            Control.namespace_key == namespace_key,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        control = cast(Control | None, result.scalars().first())
        if control is None:
            raise NotFoundError(
                error_code=ErrorCode.CONTROL_NOT_FOUND,
                detail=f"Control with ID '{control_id}' not found",
                resource="Control",
                resource_id=str(control_id),
                hint="Verify the control ID is correct and the control has been created.",
            )
        return control

    async def get_active_control_or_404(
        self,
        control_id: int,
        *,
        for_update: bool = False,
        namespace_key: str,
    ) -> Control:
        """Load an active control row or raise CONTROL_NOT_FOUND.

        The lookup is scoped to the supplied namespace; a control that
        exists only in another namespace surfaces as 404
        (non-disclosing).
        """
        stmt = select(Control).where(
            Control.id == control_id,
            Control.namespace_key == namespace_key,
            Control.deleted_at.is_(None),
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        control = cast(Control | None, result.scalars().first())
        if control is None:
            raise NotFoundError(
                error_code=ErrorCode.CONTROL_NOT_FOUND,
                detail=f"Control with ID '{control_id}' not found",
                resource="Control",
                resource_id=str(control_id),
                hint="Verify the control ID is correct and the control has been created.",
            )
        return control

    async def active_control_name_exists(
        self,
        name: str,
        *,
        namespace_key: str,
        exclude_control_id: int | None = None,
    ) -> bool:
        """Return whether an active control already uses the provided name."""
        stmt = select(Control.id).where(
            Control.namespace_key == namespace_key,
            Control.name == name,
            Control.deleted_at.is_(None),
        )
        if exclude_control_id is not None:
            stmt = stmt.where(Control.id != exclude_control_id)
        result = await self._db.execute(stmt)
        return result.first() is not None

    async def create_version(
        self,
        control: Control,
        *,
        event_type: str,
        note: str,
    ) -> ControlVersion:
        """Append a new immutable version row for the current control state."""
        await self._db.flush()
        await self._lock_control_row(control.id)

        next_version_num = await self._next_version_num(control.id)
        version = ControlVersion(
            control_id=control.id,
            version_num=next_version_num,
            event_type=event_type,
            snapshot=self._build_snapshot(control),
            note=note,
        )
        self._db.add(version)
        await self._db.flush()
        return version

    async def list_versions(
        self,
        control_id: int,
        *,
        namespace_key: str,
        cursor: int | None,
        limit: int,
    ) -> ControlVersionPage:
        """Return control versions newest-first with cursor pagination."""
        await self.get_control_or_404(control_id, namespace_key=namespace_key)

        total_result = await self._db.execute(
            select(func.count())
            .select_from(ControlVersion)
            .where(ControlVersion.control_id == control_id)
        )
        total = cast(int, total_result.scalar_one())

        stmt = (
            select(ControlVersion)
            .where(ControlVersion.control_id == control_id)
            .order_by(ControlVersion.version_num.desc())
        )
        if cursor is not None:
            stmt = stmt.where(ControlVersion.version_num < cursor)

        result = await self._db.execute(stmt.limit(limit + 1))
        versions: list[ControlVersion] = list(result.scalars().all())

        has_more = len(versions) > limit
        if has_more:
            versions = versions[:-1]

        next_cursor: str | None = None
        if has_more and versions:
            next_cursor = str(versions[-1].version_num)

        return ControlVersionPage(
            versions=versions,
            total=total,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def get_version_or_404(
        self, control_id: int, version_num: int, *, namespace_key: str
    ) -> ControlVersion:
        """Load a specific version row for a control."""
        await self.get_control_or_404(control_id, namespace_key=namespace_key)

        result = await self._db.execute(
            select(ControlVersion).where(
                ControlVersion.control_id == control_id,
                ControlVersion.version_num == version_num,
            )
        )
        version = cast(ControlVersion | None, result.scalars().first())
        if version is None:
            raise NotFoundError(
                error_code=ErrorCode.CONTROL_VERSION_NOT_FOUND,
                detail=(f"Version '{version_num}' for control with ID '{control_id}' not found"),
                resource="ControlVersion",
                resource_id=f"{control_id}:{version_num}",
                hint="Verify the control ID and version number are correct.",
            )
        return version

    async def list_controls_for_policy(
        self,
        policy_id: int,
        *,
        namespace_key: str | None = None,
    ) -> list[Control]:
        """Return DB control rows directly associated with a policy.

        When ``namespace_key`` is supplied, both the association rows
        and the joined controls are scoped to that namespace so a
        request in one namespace cannot read controls bound to a
        same-id policy in another.
        """
        stmt = (
            select(Control)
            .join(policy_controls, Control.id == policy_controls.c.control_id)
            .where(policy_controls.c.policy_id == policy_id, Control.deleted_at.is_(None))
            .order_by(Control.id)
        )
        if namespace_key is not None:
            stmt = stmt.where(
                policy_controls.c.namespace_key == namespace_key,
                Control.namespace_key == namespace_key,
            )
        result = await self._db.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_policy_control_ids(self, policy_id: int, *, namespace_key: str) -> list[int]:
        """Return active control IDs directly associated with a policy."""
        result = await self._db.execute(
            select(policy_controls.c.control_id)
            .join(Control, Control.id == policy_controls.c.control_id)
            .where(
                policy_controls.c.namespace_key == namespace_key,
                policy_controls.c.policy_id == policy_id,
                Control.namespace_key == namespace_key,
                Control.deleted_at.is_(None),
            )
            .order_by(policy_controls.c.control_id)
        )
        return [cast(int, row[0]) for row in result.all()]

    async def list_controls_for_agent(
        self,
        agent_name: str,
        *,
        namespace_key: str,
        target_type: str | None = None,
        target_id: str | None = None,
        allow_invalid_step_name_regex: bool = False,
        rendered_state: AgentControlRenderedState = "rendered",
        enabled_state: AgentControlEnabledState = "enabled",
    ) -> list[APIControl]:
        """Return API control models for controls effective for an agent.

        The effective set is the de-duplicated union of:
        - controls inherited from all assigned policies
        - controls directly associated with the agent
        - when ``target_type`` and ``target_id`` are both supplied, controls
          attached to that target through enabled bindings in the same
          namespace

        ``namespace_key`` scopes every joined table; bindings, agent
        attachments, policies, and the controls themselves must all live in
        the supplied namespace.

        By default, only active controls are returned. "Active" means rendered
        and enabled. Callers can broaden the returned set via rendered_state and
        enabled_state filters. Filters intersect, so unrendered drafts require
        rendered_state="unrendered" together with enabled_state="all" or
        enabled_state="disabled".

        Note: Any corrupted associated control row triggers APIValidationError,
        even if filters would otherwise exclude it.
        """
        db_controls = await self._list_db_controls_for_agent(
            agent_name,
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
        )

        parsed_controls = [
            parse_associated_control_or_api_error(
                control,
                allow_invalid_step_name_regex=allow_invalid_step_name_regex,
            )
            for control in db_controls
        ]
        return [
            control
            for control in parsed_controls
            if _matches_rendered_state(control, rendered_state)
            and _matches_enabled_state(control, enabled_state)
        ]

    async def list_runtime_controls_for_agent(
        self,
        agent_name: str,
        *,
        namespace_key: str,
        target_type: str | None = None,
        target_id: str | None = None,
        allow_invalid_step_name_regex: bool = False,
    ) -> list[RuntimeControl]:
        """Return runtime-parsed controls for evaluation hot paths.

        See :meth:`list_controls_for_agent` for the merge semantics; this
        method applies the same selection logic and parses each row into the
        runtime form used by the evaluation engine.
        """
        db_controls = await self._list_db_controls_for_agent(
            agent_name,
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
        )
        return parse_runtime_controls(
            db_controls,
            allow_invalid_step_name_regex=allow_invalid_step_name_regex,
        )

    async def list_controls_page(
        self,
        *,
        namespace_key: str,
        cursor: int | None,
        limit: int,
        name: str | None,
        enabled: bool | None,
        template_backed: bool | None,
        cloned: bool | None,
        step_type: str | None,
        stage: str | None,
        execution: str | None,
        tag: str | None,
        attachment_target_type: str | None = None,
        attachment_target_id: str | None = None,
    ) -> ControlListPage:
        """Return paginated active controls for the browse endpoint."""
        query = (
