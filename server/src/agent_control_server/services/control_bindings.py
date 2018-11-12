"""Persistence and resolution helpers for the ``control_bindings`` table.

Each binding row attaches one control to one target inside a namespace.
Per-agent overrides and exemptions within a target are intentionally not
modeled at this stage; see ``ControlBinding`` for the documented forward
paths if and when they become a product requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from agent_control_models.controls import ControlDefinitionRuntime
from agent_control_models.errors import ErrorCode
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import BadRequestError, ConflictError, NotFoundError
from ..models import Control, ControlBinding
from .evaluator_utils import parse_evaluator_ref_full


@dataclass(frozen=True)
class ControlBindingListPage:
    """Paginated control-binding rows for list endpoints."""

    bindings: list[ControlBinding]
    total: int
    has_more: bool
    next_cursor: str | None


class ControlBindingsService:
    """Persistence and resolution helpers for control bindings."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_binding(
        self,
        *,
        namespace_key: str,
        target_type: str,
        target_id: str,
        control_id: int,
        enabled: bool = True,
    ) -> ControlBinding:
        """Insert a new binding row.

        Raises ``NotFoundError`` if the referenced control does not exist in
        the same namespace, and ``ConflictError`` if a binding for the same
        ``(namespace_key, target_type, target_id, control_id)`` already
        exists.
        """
        await self._require_control(namespace_key=namespace_key, control_id=control_id)
        binding = ControlBinding(
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
            control_id=control_id,
            enabled=enabled,
        )
        # ``begin_nested`` opens a SAVEPOINT so a unique-constraint
        # collision rolls back only the conflicting insert. A bare
        # ``session.rollback()`` would discard every pending change in
        # the surrounding transaction, including unrelated writes from a
        # caller that composed this service after another flush.
        try:
            async with self._db.begin_nested():
                self._db.add(binding)
                await self._db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                error_code=ErrorCode.CONTROL_BINDING_CONFLICT,
                detail=(
                    "A binding for this (target_type, target_id, control_id) "
                    "already exists in this namespace."
                ),
                resource="ControlBinding",
                hint="Update the existing binding instead of creating a new one.",
            ) from exc
        return binding

    async def upsert_by_natural_key(
        self,
        *,
        namespace_key: str,
        target_type: str,
        target_id: str,
        control_id: int,
        enabled: bool = True,
    ) -> tuple[ControlBinding, bool]:
        """Idempotent attach by natural key.

        Returns ``(binding, created)``. If a binding for the same
        ``(namespace_key, target_type, target_id, control_id)`` already
        exists, ``enabled`` is updated to the supplied value; otherwise a
        new binding is created.

        Concurrent callers for the same natural key are handled safely: the
        loser of the unique-constraint race rolls back its insert, re-reads
        the winning row, and applies its ``enabled`` value as an update. Both
        calls return successfully; the create flag is true only for the
        caller whose insert actually wrote the row.
        """
        await self._require_control(namespace_key=namespace_key, control_id=control_id)
        existing = await self._find_by_natural_key(
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
            control_id=control_id,
        )
        if existing is not None:
            existing.enabled = enabled
            await self._db.flush()
            return existing, False

        binding = ControlBinding(
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
            control_id=control_id,
            enabled=enabled,
        )
        # ``begin_nested`` opens a SAVEPOINT so a unique-constraint
        # collision rolls back only the conflicting insert. A bare
        # ``session.rollback()`` would discard every pending change in
        # the surrounding transaction, including unrelated writes from a
        # caller that composed this service after another flush.
        try:
            async with self._db.begin_nested():
                self._db.add(binding)
                await self._db.flush()
            return binding, True
        except IntegrityError:
            # Concurrent insert won the natural-key race. Re-read the
            # winning row and apply the requested enabled value; the
            # surrounding transaction is intact because the rollback was
            # scoped to the savepoint above.
            existing = await self._find_by_natural_key(
                namespace_key=namespace_key,
                target_type=target_type,
                target_id=target_id,
                control_id=control_id,
            )
            if existing is None:
                raise
            existing.enabled = enabled
            await self._db.flush()
            return existing, False

    async def delete_by_natural_key(
        self,
        *,
        namespace_key: str,
        target_type: str,
        target_id: str,
        control_id: int,
    ) -> bool:
        """Idempotent detach by natural key. Returns whether a row was deleted."""
        existing = await self._find_by_natural_key(
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
            control_id=control_id,
        )
        if existing is None:
            return False
        await self._db.delete(existing)
        await self._db.flush()
        return True

    async def set_enabled_by_natural_key(
        self,
        *,
        namespace_key: str,
        target_type: str,
        target_id: str,
        control_id: int,
        enabled: bool,
    ) -> ControlBinding:
        """Update an existing binding by natural key.

        Unlike ``upsert_by_natural_key``, this never creates a binding.
        It is intended for target-scoped callers that need to toggle an
        already-attached control while preserving a clear 404 for missing
        attachments.
        """
        existing = await self._find_by_natural_key(
            namespace_key=namespace_key,
            target_type=target_type,
            target_id=target_id,
            control_id=control_id,
        )
        if existing is None:
            raise NotFoundError(
                error_code=ErrorCode.CONTROL_BINDING_NOT_FOUND,
                detail=(
                    "Control binding not found for the supplied "
                    "(target_type, target_id, control_id)."
                ),
                resource="ControlBinding",
                hint=(
                    "Verify the target and control IDs, or attach the control "
                    "before updating the binding."
                ),
            )
        existing.enabled = enabled
        await self._db.flush()
        return existing

    async def _find_by_natural_key(
