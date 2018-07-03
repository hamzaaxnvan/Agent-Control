"""namespace scoping and control bindings

Adds a `namespace_key` scoping column to all six core tables, replaces
single-column uniqueness with namespace-scoped composite uniqueness, converts
foreign keys on association tables to composite same-namespace foreign keys,
and creates the new `control_bindings` table for target-attached controls.

OSS / single-namespace deployments are preserved by the `'default'` server
default on every new `namespace_key` column.

Downgrade caveat: once cross-namespace data exists (two rows with the same
natural-key in different namespaces), restoring the original global
single-column uniqueness is not possible. The downgrade asserts that no such
duplicates exist and aborts with a clear error if they do.

Revision ID: a7f3b1e0d9c5
Revises: c1e9f9c4a1d2
Create Date: 2026-04-27 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7f3b1e0d9c5"
down_revision = "c1e9f9c4a1d2"
branch_labels = None
depends_on = None


_NAMESPACE_DEFAULT = sa.text("'default'")


def upgrade() -> None:
    # 1. Add namespace_key column to all six core tables.
    for table in (
        "agents",
        "controls",
        "policies",
        "agent_controls",
        "agent_policies",
        "policy_controls",
    ):
        op.add_column(
            table,
            sa.Column(
                "namespace_key",
                sa.String(255),
                nullable=False,
                server_default=_NAMESPACE_DEFAULT,
            ),
        )

    # 2. Drop existing foreign keys on association tables. All are being
    #    replaced with composite same-namespace foreign keys.
    op.drop_constraint(
        "agent_controls_agent_name_fkey", "agent_controls", type_="foreignkey"
    )
    op.drop_constraint(
        "agent_controls_control_id_fkey", "agent_controls", type_="foreignkey"
    )
    op.drop_constraint(
        "agent_policies_agent_name_fkey", "agent_policies", type_="foreignkey"
    )
    op.drop_constraint(
        "agent_policies_policy_id_fkey", "agent_policies", type_="foreignkey"
    )
    op.drop_constraint(
        "policy_controls_policy_id_fkey", "policy_controls", type_="foreignkey"
    )
    op.drop_constraint(
        "policy_controls_control_id_fkey", "policy_controls", type_="foreignkey"
    )

    # 3. Drop existing primary keys, unique constraints, and partial unique
    #    index that are about to be replaced.
    op.drop_constraint("agents_pkey", "agents", type_="primary")
    op.drop_constraint("policies_name_key", "policies", type_="unique")
    op.drop_index("idx_controls_name_active", table_name="controls")
