"""namespace observability events

Revision ID: b6f4c2d8e9a1
Revises: a7f3b1e0d9c5
Create Date: 2026-05-14 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b6f4c2d8e9a1"
down_revision = "a7f3b1e0d9c5"
branch_labels = None
depends_on = None


_EVENT_TABLE = "control_execution_events"
_NAMESPACE_COLUMN = "namespace_key"
_TARGET_PK_COLUMNS = ["namespace_key", "control_execution_id"]
_LEGACY_PK_COLUMNS = ["control_execution_id"]


def _column_names() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_EVENT_TABLE)}


def _replace_primary_key(columns: list[str]) -> None:
    pk = sa.inspect(op.get_bind()).get_pk_constraint(_EVENT_TABLE)
    current_columns = list(pk.get("constrained_columns") or [])
    if current_columns == columns:
        return

    constraint_name = pk.get("name")
