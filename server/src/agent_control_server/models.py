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
