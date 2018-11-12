"""agent policy m2m and direct agent controls

Revision ID: 4b8c7d4a1f31
Revises: 58920e6807fe
Create Date: 2026-03-02 16:15:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4b8c7d4a1f31"
down_revision = "58920e6807fe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_controls",
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["agent_name"], ["agents.name"]),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"]),
        sa.PrimaryKeyConstraint("agent_name", "control_id"),
    )
    op.create_index(op.f("ix_agent_controls_agent_name"), "agent_controls", ["agent_name"])
    op.create_index(op.f("ix_agent_controls_control_id"), "agent_controls", ["control_id"])

    op.create_table(
        "agent_policies",
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["agent_name"], ["agents.name"]),
