import datetime as dt
from typing import Any

from agent_control_models.agent import StepSchema, normalize_agent_name
from agent_control_models.base import BaseModel
from agent_control_models.server import EvaluatorSchema
from pydantic import Field
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .db import Base

DEFAULT_NAMESPACE_KEY = "default"
_NAMESPACE_SERVER_DEFAULT = text("'default'")


class AgentData(BaseModel):
    """Agent metadata stored in JSONB."""

    agent_metadata: dict[str, Any]
    steps: list[StepSchema] = Field(default_factory=list)
    evaluators: list[EvaluatorSchema] = Field(default_factory=list)


# Association table for Policy <> Control many-to-many relationship.
# Composite FKs enforce same-namespace references on both sides.
policy_controls: Table = Table(
    "policy_controls",
    Base.metadata,
    Column(
        "namespace_key",
        String(255),
        primary_key=True,
        nullable=False,
        server_default=_NAMESPACE_SERVER_DEFAULT,
    ),
    Column("policy_id", Integer, primary_key=True, index=True),
    Column("control_id", Integer, primary_key=True, index=True),
    ForeignKeyConstraint(
        ["namespace_key", "policy_id"],
        ["policies.namespace_key", "policies.id"],
        name="policy_controls_policy_fkey",
    ),
    ForeignKeyConstraint(
        ["namespace_key", "control_id"],
        ["controls.namespace_key", "controls.id"],
        name="policy_controls_control_fkey",
    ),
)

# Association table for Agent <> Policy many-to-many relationship.
agent_policies: Table = Table(
    "agent_policies",
    Base.metadata,
    Column(
        "namespace_key",
        String(255),
        primary_key=True,
        nullable=False,
        server_default=_NAMESPACE_SERVER_DEFAULT,
    ),
    Column("agent_name", String(255), primary_key=True, index=True),
    Column("policy_id", Integer, primary_key=True, index=True),
    ForeignKeyConstraint(
        ["namespace_key", "agent_name"],
        ["agents.namespace_key", "agents.name"],
        name="agent_policies_agent_fkey",
    ),
    ForeignKeyConstraint(
        ["namespace_key", "policy_id"],
        ["policies.namespace_key", "policies.id"],
        name="agent_policies_policy_fkey",
    ),
)

# Association table for Agent <> Control direct many-to-many relationship.
agent_controls: Table = Table(
    "agent_controls",
    Base.metadata,
    Column(
        "namespace_key",
        String(255),
        primary_key=True,
        nullable=False,
        server_default=_NAMESPACE_SERVER_DEFAULT,
    ),
    Column("agent_name", String(255), primary_key=True, index=True),
    Column("control_id", Integer, primary_key=True, index=True),
    ForeignKeyConstraint(
        ["namespace_key", "agent_name"],
        ["agents.namespace_key", "agents.name"],
        name="agent_controls_agent_fkey",
    ),
    ForeignKeyConstraint(
        ["namespace_key", "control_id"],
        ["controls.namespace_key", "controls.id"],
        name="agent_controls_control_fkey",
    ),
)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint(
            "namespace_key", "name", name="uq_policies_namespace_name"
        ),
        UniqueConstraint(
            "namespace_key", "id", name="uq_policies_namespace_id"
        ),
        # Plain index on name preserves name-only lookup performance while
        # service code is still namespace-blind.
        Index("ix_policies_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace_key: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default=_NAMESPACE_SERVER_DEFAULT
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agents: Mapped[list["Agent"]] = relationship(
        "Agent", secondary=lambda: agent_policies, back_populates="policies"
    )
    # Many-to-many: Policy <> Control (direct relationship, no ControlSet layer)
    controls: Mapped[list["Control"]] = relationship(
        "Control", secondary=lambda: policy_controls, back_populates="policies"
    )


class Control(Base):
    __tablename__ = "controls"
    __table_args__ = (
        Index(
            "idx_controls_namespace_name_active",
            "namespace_key",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        UniqueConstraint(
            "namespace_key", "id", name="uq_controls_namespace_id"
        ),
        # Hard deletes of clone sources are restricted. The request path
        # soft-deletes controls so clone lineage remains intact.
        ForeignKeyConstraint(
            ["namespace_key", "cloned_from_control_id"],
            ["controls.namespace_key", "controls.id"],
            name="controls_cloned_from_control_fkey",
        ),
        # Plain partial index on name preserves name-only lookup performance
        # while service code is still namespace-blind. Mirrors the pattern
        # used for agents and policies; the partial filter matches the
        # existing call sites that already require deleted_at IS NULL.
        Index(
            "ix_controls_name",
            "name",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_controls_cloned_from",
            "namespace_key",
            "cloned_from_control_id",
            postgresql_where=text("cloned_from_control_id IS NOT NULL"),
            sqlite_where=text("cloned_from_control_id IS NOT NULL"),
        ),
        Index(
            "idx_controls_namespace_seed_source",
            "namespace_key",
            "seed_source_id",
            unique=True,
            postgresql_where=text("seed_source_id IS NOT NULL"),
            sqlite_where=text("seed_source_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace_key: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default=_NAMESPACE_SERVER_DEFAULT
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # JSONB payload describing control specifics
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    cloned_from_control_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    seed_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seed_opted_out_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
