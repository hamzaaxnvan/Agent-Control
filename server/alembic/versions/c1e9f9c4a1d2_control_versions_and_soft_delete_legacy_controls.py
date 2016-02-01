"""add control versions and soft-delete unusable legacy controls

Revision ID: c1e9f9c4a1d2
Revises: 5f2b5f4e1a90
Create Date: 2026-04-15 12:00:00.000000

"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import sqlalchemy as sa
from alembic import op
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from agent_control_models import ControlDefinition, UnrenderedTemplateControl

# revision identifiers, used by Alembic.
revision = "c1e9f9c4a1d2"
down_revision = "5f2b5f4e1a90"
branch_labels = None
depends_on = None

_logger = logging.getLogger("alembic.runtime.migration")

_BACKFILL_NOTE = "Backfilled from existing control"


def _classify_control_payload(data: Any) -> tuple[bool, str | None]:
    """Return whether a legacy control payload is still usable."""
    if data == {}:
        return False, "empty payload"
    if not isinstance(data, dict):
        return False, "invalid control payload"

    try:
        UnrenderedTemplateControl.model_validate(data)
    except ValidationError:
        pass
    else:
        return True, None

    try:
        ControlDefinition.model_validate(data)
    except ValidationError:
        return False, "invalid control payload"

    return True, None


def _snapshot_payload(
