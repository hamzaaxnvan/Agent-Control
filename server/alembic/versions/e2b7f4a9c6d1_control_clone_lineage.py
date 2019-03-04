"""control clone lineage

Revision ID: e2b7f4a9c6d1
Revises: b6f4c2d8e9a1
Create Date: 2026-05-19 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2b7f4a9c6d1"
down_revision = "b6f4c2d8e9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "controls",
        sa.Column("cloned_from_control_id", sa.Integer(), nullable=True),
    )
    # No ON DELETE action: hard deletes of clone sources are restricted.
