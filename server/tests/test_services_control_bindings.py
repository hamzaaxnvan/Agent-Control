"""Coverage for ``ControlBindingsService`` upsert/concurrency paths.

Effective-controls resolution now lives in
``ControlService.list_controls_for_agent``; the merge semantics for the
``control_bindings`` source are exercised in ``test_services_controls``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agent_control_server.models import Control, ControlBinding
from agent_control_server.services.control_bindings import ControlBindingsService

from .utils import VALID_CONTROL_PAYLOAD


def _control_name() -> str:
    return f"control-{uuid.uuid4().hex[:12]}"


async def _add_control(
    session: AsyncSession,
    *,
    namespace_key: str = "default",
) -> Control:
    control = Control(
        namespace_key=namespace_key,
        name=_control_name(),
        data=VALID_CONTROL_PAYLOAD,
        deleted_at=None,
    )
    session.add(control)
    await session.flush()
    return control


@pytest.mark.asyncio
async def test_upsert_handles_integrity_error_from_concurrent_flush(
