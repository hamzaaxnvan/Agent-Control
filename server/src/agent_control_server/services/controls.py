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
