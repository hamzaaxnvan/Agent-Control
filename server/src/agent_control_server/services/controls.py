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
            select(Control)
            .where(Control.namespace_key == namespace_key, Control.deleted_at.is_(None))
            .order_by(Control.id.desc())
        )
        query = self._apply_control_list_filters(
            query,
            name=name,
            enabled=enabled,
            template_backed=template_backed,
            cloned=cloned,
            step_type=step_type,
            stage=stage,
            execution=execution,
            tag=tag,
        )
        query = self._apply_control_attachment_filters(
            query,
            namespace_key=namespace_key,
            target_type=attachment_target_type,
            target_id=attachment_target_id,
        )
        if cursor is not None:
            query = query.where(Control.id < cursor)

        result = await self._db.execute(query.limit(limit + 1))
        controls: list[Control] = list(result.scalars().all())

        total_query = (
            select(func.count())
            .select_from(Control)
            .where(Control.namespace_key == namespace_key, Control.deleted_at.is_(None))
        )
        total_query = self._apply_control_list_filters(
            total_query,
            name=name,
            enabled=enabled,
            template_backed=template_backed,
            cloned=cloned,
            step_type=step_type,
            stage=stage,
            execution=execution,
            tag=tag,
        )
        total_query = self._apply_control_attachment_filters(
            total_query,
            namespace_key=namespace_key,
            target_type=attachment_target_type,
            target_id=attachment_target_id,
        )
        total_result = await self._db.execute(total_query)
        total = cast(int, total_result.scalar_one())

        has_more = len(controls) > limit
        if has_more:
            controls = controls[:-1]

        next_cursor: str | None = None
        if has_more and controls:
            next_cursor = str(controls[-1].id)

        return ControlListPage(
            controls=controls,
            total=total,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def list_control_usage(
        self, control_ids: Sequence[int], *, namespace_key: str
    ) -> dict[int, ControlUsage]:
        """Return representative agent usage and usage counts for the provided controls."""
        if not control_ids:
            return {}

        usage_names: dict[int, set[str]] = {control_id: set() for control_id in control_ids}
        policy_agents_query = (
            select(
                policy_controls.c.control_id,
                agent_policies.c.agent_name,
            )
            .select_from(policy_controls)
            .join(
                agent_policies,
                (policy_controls.c.policy_id == agent_policies.c.policy_id)
                & (policy_controls.c.namespace_key == agent_policies.c.namespace_key),
            )
            .where(
                policy_controls.c.namespace_key == namespace_key,
                agent_policies.c.namespace_key == namespace_key,
                policy_controls.c.control_id.in_(control_ids),
            )
        )
        direct_agents_query = (
            select(
                agent_controls.c.control_id,
                agent_controls.c.agent_name,
            )
            .select_from(agent_controls)
            .where(
                agent_controls.c.namespace_key == namespace_key,
                agent_controls.c.control_id.in_(control_ids),
            )
        )
        agents_result = await self._db.execute(union_all(policy_agents_query, direct_agents_query))
        for control_id, agent_name in agents_result.all():
            usage_names[cast(int, control_id)].add(cast(str, agent_name))

        return {
            control_id: ControlUsage(
                representative_agent_name=min(agent_names) if agent_names else None,
                used_by_agents_count=len(agent_names),
            )
            for control_id, agent_names in usage_names.items()
        }

    async def list_control_attachments(
        self,
        control_ids: Sequence[int],
        *,
        namespace_key: str,
        target_type: str | None = None,
        target_id: str | None = None,
        include_targets: bool = True,
    ) -> dict[int, ControlAttachmentSet]:
        """Return direct policy, direct agent, and target attachments for controls."""
        if not control_ids:
            return {}

        unique_control_ids = list(dict.fromkeys(control_ids))
        policy_ids_by_control: dict[int, set[int]] = {
            control_id: set() for control_id in unique_control_ids
        }
        agent_names_by_control: dict[int, set[str]] = {
            control_id: set() for control_id in unique_control_ids
        }
        targets_by_control: dict[int, list[ControlTargetAttachment]] = {
            control_id: [] for control_id in unique_control_ids
        }
        target_totals_by_control: dict[int, int] = {
            control_id: 0 for control_id in unique_control_ids
        }

        policy_result = await self._db.execute(
            select(policy_controls.c.control_id, policy_controls.c.policy_id).where(
                policy_controls.c.namespace_key == namespace_key,
                policy_controls.c.control_id.in_(unique_control_ids),
            )
        )
        for control_id, policy_id in policy_result.all():
            policy_ids_by_control[cast(int, control_id)].add(cast(int, policy_id))

        agent_result = await self._db.execute(
            select(agent_controls.c.control_id, agent_controls.c.agent_name).where(
                agent_controls.c.namespace_key == namespace_key,
                agent_controls.c.control_id.in_(unique_control_ids),
            )
        )
        for control_id, agent_name in agent_result.all():
            agent_names_by_control[cast(int, control_id)].add(cast(str, agent_name))

        if include_targets:
            target_rank = func.row_number().over(
                partition_by=ControlBinding.control_id,
                order_by=ControlBinding.id.desc(),
            ).label("target_rank")
            target_total = func.count().over(
                partition_by=ControlBinding.control_id
            ).label("target_total")
            target_query = (
                select(
                    ControlBinding.control_id,
                    ControlBinding.id,
                    ControlBinding.target_type,
                    ControlBinding.target_id,
                    ControlBinding.enabled,
                    target_rank,
                    target_total,
                )
                .where(
                    ControlBinding.namespace_key == namespace_key,
                    ControlBinding.control_id.in_(unique_control_ids),
                )
            )
            if target_type is not None:
                target_query = target_query.where(ControlBinding.target_type == target_type)
            if target_id is not None:
                target_query = target_query.where(ControlBinding.target_id == target_id)
            target_rows = target_query.subquery()
            target_result = await self._db.execute(
                select(
                    target_rows.c.control_id,
                    target_rows.c.id,
                    target_rows.c.target_type,
                    target_rows.c.target_id,
                    target_rows.c.enabled,
                    target_rows.c.target_total,
                )
                .where(
                    target_rows.c.target_rank
                    <= _MAX_INLINE_TARGET_ATTACHMENTS_PER_CONTROL
                )
                .order_by(target_rows.c.control_id, target_rows.c.target_rank)
            )
            for (
                control_id,
                binding_id,
                binding_target_type,
                binding_target_id,
                enabled,
                target_total,
            ) in (
                target_result.all()
            ):
                typed_control_id = cast(int, control_id)
                target_totals_by_control[typed_control_id] = cast(int, target_total)
                targets_by_control[typed_control_id].append(
                    ControlTargetAttachment(
                        binding_id=cast(int, binding_id),
                        target_type=cast(str, binding_target_type),
                        target_id=cast(str, binding_target_id),
                        enabled=cast(bool, enabled),
                    )
                )

        return {
            control_id: ControlAttachmentSet(
                policy_ids=sorted(policy_ids_by_control[control_id]),
                agent_names=sorted(agent_names_by_control[control_id]),
                targets=targets_by_control[control_id],
                targets_total=target_totals_by_control[control_id],
                targets_truncated=(
                    target_totals_by_control[control_id]
                    > len(targets_by_control[control_id])
                ),
            )
            for control_id in unique_control_ids
        }

    async def list_active_control_counts_by_agent(
        self,
        agent_names: Sequence[str],
        *,
        namespace_key: str,
